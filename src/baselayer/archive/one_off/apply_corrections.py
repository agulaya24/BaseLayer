"""
Correction Propagation Tool (D-021: Fix Once, Fixed Forever)

Applies user corrections to the memory database. Two modes:

  Batch mode:   python apply_corrections.py --batch ../data/corrections_v1.json
  Interactive:  python apply_corrections.py --interactive
  Show applied: python apply_corrections.py --show

User corrections are:
  - Stored permanently in the `user_corrections` table (survives extraction resets)
  - Applied as the highest authority (confidence = 1.0, source = 'user_correction')
  - Used as a guard during future extraction runs to block re-extraction of wrong facts

Five correction types:
  DELETE      — fact is wrong, remove it
  REPLACE     — fact is wrong, here's the correct version
  REATTRIBUTE — fact belongs to someone else (wife, friend, etc.)
  ADD         — fact is missing, add it
  ANNOTATE    — fact is correct but needs context (e.g., sentiment)
"""

import contextlib
import sys
import io
import sqlite3
import json
import time
import uuid
import argparse
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from config import DATABASE_FILE, VECTORS_DIR, EMBEDDING_MODEL


# ---------------------------------------------------------------------------
# Database Helpers
# ---------------------------------------------------------------------------

def ensure_tables(conn):
    """Make sure user_corrections table and source column exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_corrections (
            id TEXT PRIMARY KEY,
            correction_type TEXT NOT NULL,
            original_fact_id TEXT,
            original_fact_text TEXT,
            corrected_fact_text TEXT,
            corrected_category TEXT,
            corrected_subject TEXT,
            annotation TEXT,
            match_patterns TEXT,
            created_at REAL NOT NULL,
            notes TEXT
        )
    """)
    try:
        conn.execute("ALTER TABLE memory_facts ADD COLUMN source TEXT DEFAULT 'extraction'")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists
    conn.commit()


def search_facts(conn, keyword):
    """Find active facts matching a keyword (case-insensitive)."""
    rows = conn.execute("""
        SELECT id, fact_text, category, confidence, source
        FROM memory_facts
        WHERE fact_text LIKE ? AND superseded_by IS NULL
        ORDER BY confidence DESC
    """, (f"%{keyword}%",)).fetchall()
    return [{"id": r[0], "text": r[1], "category": r[2], "confidence": r[3], "source": r[4]} for r in rows]


def find_facts_by_id_prefix(conn, prefix):
    """Find facts whose ID starts with a given prefix (first 8 chars)."""
    rows = conn.execute("""
        SELECT id, fact_text, category, confidence, superseded_by
        FROM memory_facts
        WHERE id LIKE ?
    """, (f"{prefix}%",)).fetchall()
    return [{"id": r[0], "text": r[1], "category": r[2], "confidence": r[3], "superseded_by": r[4]} for r in rows]


def supersede_fact(conn, fact_id, superseded_by_value):
    """Mark a fact as superseded."""
    conn.execute("""
        UPDATE memory_facts SET superseded_by = ?, updated_at = ?
        WHERE id = ?
    """, (superseded_by_value, time.time(), fact_id))


def insert_corrected_fact(conn, fact_text, category, source="user_correction", conv_id=None):
    """Insert a new fact with user_correction source and confidence 1.0."""
    fact_id = str(uuid.uuid4())
    now = time.time()
    conn.execute("""
        INSERT INTO memory_facts
        (id, fact_text, category, confidence, source_conversation_id,
         created_at, updated_at, superseded_by, source)
        VALUES (?, ?, ?, 1.0, ?, ?, ?, NULL, ?)
    """, (fact_id, fact_text, category, conv_id, now, now, source))
    return fact_id


def store_correction(conn, correction_id, correction_type, original_fact_id,
                     original_fact_text, corrected_fact_text, corrected_category,
                     corrected_subject, annotation, match_patterns, notes):
    """Store a correction in the user_corrections table."""
    conn.execute("""
        INSERT OR REPLACE INTO user_corrections
        (id, correction_type, original_fact_id, original_fact_text,
         corrected_fact_text, corrected_category, corrected_subject,
         annotation, match_patterns, created_at, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        correction_id, correction_type, original_fact_id, original_fact_text,
        corrected_fact_text, corrected_category, corrected_subject,
        annotation, json.dumps(match_patterns) if isinstance(match_patterns, list) else match_patterns,
        time.time(), notes
    ))


# ---------------------------------------------------------------------------
# ChromaDB Sync
# ---------------------------------------------------------------------------

def get_chromadb_collection():
    """Load ChromaDB facts collection and embedding model (centralized singleton)."""
    try:
        import chromadb
        from api_client import get_embedding_model

        model = get_embedding_model()
        if model is None:
            print("  WARNING: Embedding model not available. Skipping vector sync.")
            return None, None

        client = chromadb.PersistentClient(path=str(VECTORS_DIR))

        try:
            collection = client.get_collection("memory_facts")
        except Exception:
            collection = client.create_collection(
                name="memory_facts",
                metadata={"hnsw:space": "cosine", "description": "Extracted personal facts (AUDN pipeline)"}
            )

        return collection, model
    except ImportError:
        print("  WARNING: chromadb not available. Skipping vector sync.")
        return None, None


def sync_chromadb(removed_ids, new_facts, collection, model):
    """Remove old fact embeddings and add new ones."""
    if collection is None or model is None:
        return

    # Remove superseded facts from vector store
    if removed_ids:
        # ChromaDB delete only works with IDs that exist — filter first
        existing = set()
        for rid in removed_ids:
            try:
                result = collection.get(ids=[rid])
                if result and result["ids"]:
                    existing.add(rid)
            except Exception:
                pass

        if existing:
            collection.delete(ids=list(existing))
            print(f"  Removed {len(existing)} facts from ChromaDB")

    # Add new corrected facts
    if new_facts:
        for fact in new_facts:
            embedding = model.encode([fact["text"]]).tolist()
            collection.add(
                ids=[fact["id"]],
                embeddings=embedding,
                documents=[fact["text"]],
                metadatas=[{"fact_id": fact["id"], "category": fact["category"]}],
            )
        print(f"  Added {len(new_facts)} corrected facts to ChromaDB")


# ---------------------------------------------------------------------------
# Correction Appliers
# ---------------------------------------------------------------------------

def apply_delete(conn, correction, collection, model):
    """DELETE: Mark facts as superseded, store correction, remove from ChromaDB."""
    fact_ids = resolve_fact_ids(conn, correction)
    if not fact_ids:
        print(f"  WARNING: No matching facts found for {correction['id']}")
        return [], []

    removed_ids = []
    for fid in fact_ids:
        supersede_fact(conn, fid, "USER_DELETED")
        removed_ids.append(fid)

    store_correction(
        conn, correction["id"], "DELETE",
        fact_ids[0] if fact_ids else None,
        correction.get("original_fact_text"),
        None, None, None, None,
        correction.get("match_patterns", []),
        correction.get("notes")
    )

    sync_chromadb(removed_ids, [], collection, model)
    print(f"  DELETE {correction['id']}: superseded {len(removed_ids)} facts")
    return removed_ids, []


def apply_replace(conn, correction, collection, model):
    """REPLACE: Supersede wrong facts, insert corrected version."""
    fact_ids = resolve_fact_ids(conn, correction)
    removed_ids = []
    for fid in fact_ids:
        supersede_fact(conn, fid, "USER_CORRECTED")
        removed_ids.append(fid)

    # Insert corrected fact
    new_fact_id = insert_corrected_fact(
        conn,
        correction["corrected_fact_text"],
        correction.get("corrected_category", "biography")
    )

    store_correction(
        conn, correction["id"], "REPLACE",
        fact_ids[0] if fact_ids else None,
        correction.get("original_fact_text"),
        correction["corrected_fact_text"],
        correction.get("corrected_category"),
        None, None,
        correction.get("match_patterns", []),
        correction.get("notes")
    )

    new_facts = [{"id": new_fact_id, "text": correction["corrected_fact_text"],
                  "category": correction.get("corrected_category", "biography")}]
    sync_chromadb(removed_ids, new_facts, collection, model)
    print(f"  REPLACE {correction['id']}: superseded {len(removed_ids)}, added 1 corrected fact")
    return removed_ids, new_facts


def apply_reattribute(conn, correction, collection, model):
    """REATTRIBUTE: Supersede misattributed facts, optionally create reattributed version."""
    fact_ids = resolve_fact_ids(conn, correction)
    removed_ids = []
    for fid in fact_ids:
        supersede_fact(conn, fid, "USER_REATTRIBUTED")
        removed_ids.append(fid)

    new_facts = []
    if correction.get("corrected_fact_text"):
        new_fact_id = insert_corrected_fact(
            conn,
            correction["corrected_fact_text"],
            correction.get("corrected_category", "relationship")
        )
        new_facts.append({
            "id": new_fact_id,
            "text": correction["corrected_fact_text"],
            "category": correction.get("corrected_category", "relationship")
        })

    store_correction(
        conn, correction["id"], "REATTRIBUTE",
        fact_ids[0] if fact_ids else None,
        correction.get("original_fact_text"),
        correction.get("corrected_fact_text"),
        correction.get("corrected_category"),
        correction.get("corrected_subject"),
        None,
        correction.get("match_patterns", []),
        correction.get("notes")
    )

    sync_chromadb(removed_ids, new_facts, collection, model)
    print(f"  REATTRIBUTE {correction['id']}: superseded {len(removed_ids)}, added {len(new_facts)} reattributed fact(s)")
    return removed_ids, new_facts


def apply_add(conn, correction, collection, model):
    """ADD: Insert a new user-provided fact."""
    new_fact_id = insert_corrected_fact(
        conn,
        correction["corrected_fact_text"],
        correction.get("corrected_category", "biography")
    )

    store_correction(
        conn, correction["id"], "ADD",
        None,
        None,
        correction["corrected_fact_text"],
        correction.get("corrected_category"),
        None, None,
        correction.get("match_patterns", []),
        correction.get("notes")
    )

    new_facts = [{"id": new_fact_id, "text": correction["corrected_fact_text"],
                  "category": correction.get("corrected_category", "biography")}]
    sync_chromadb([], new_facts, collection, model)
    print(f"  ADD {correction['id']}: inserted 1 new fact")
    return [], new_facts


def apply_annotate(conn, correction, collection, model):
    """ANNOTATE: Add context/sentiment to existing facts without superseding them."""
    fact_ids = resolve_fact_ids(conn, correction)

    store_correction(
        conn, correction["id"], "ANNOTATE",
        fact_ids[0] if fact_ids else None,
        correction.get("original_fact_text"),
        None, None, None,
        correction.get("annotation"),
        correction.get("match_patterns", []),
        correction.get("notes")
    )

    print(f"  ANNOTATE {correction['id']}: annotated {len(fact_ids)} facts with: {correction.get('annotation', '')[:60]}")
    return [], []


# ---------------------------------------------------------------------------
# Fact ID Resolution
# ---------------------------------------------------------------------------

def resolve_fact_ids(conn, correction):
    """Resolve fact ID prefixes from a correction to full IDs."""
    prefixes = correction.get("original_fact_ids", [])
    full_ids = []

    for prefix in prefixes:
        matches = find_facts_by_id_prefix(conn, prefix)
        if matches:
            # Only include active facts (not already superseded)
            for m in matches:
                if m["superseded_by"] is None:
                    full_ids.append(m["id"])
        else:
            print(f"    WARNING: No fact found for ID prefix '{prefix}'")

    return full_ids


# ---------------------------------------------------------------------------
# Batch Mode
# ---------------------------------------------------------------------------

def run_batch(json_path):
    """Apply all corrections from a JSON file."""
    print("=" * 60)
    print("Correction Propagation — Batch Mode")
    print("=" * 60)

    # Load corrections file
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    corrections = data.get("corrections", [])
    print(f"\nSource: {data.get('source', 'unknown')}")
    print(f"Corrections to apply: {len(corrections)}")

    # Connect to database
    with contextlib.closing(sqlite3.connect(DATABASE_FILE)) as conn:
        ensure_tables(conn)

        # Check for already-applied corrections
        existing = set()
        for row in conn.execute("SELECT id FROM user_corrections").fetchall():
            existing.add(row[0])

        # Load ChromaDB
        print("\nLoading ChromaDB and embedding model...")
        collection, model = get_chromadb_collection()

        # Apply each correction
        total_removed = 0
        total_added = 0
        skipped = 0

        print()
        for correction in corrections:
            cid = correction["id"]
            ctype = correction["correction_type"]

            if cid in existing:
                print(f"  SKIP {cid}: already applied")
                skipped += 1
                continue

            if ctype == "DELETE":
                removed, added = apply_delete(conn, correction, collection, model)
            elif ctype == "REPLACE":
                removed, added = apply_replace(conn, correction, collection, model)
            elif ctype == "REATTRIBUTE":
                removed, added = apply_reattribute(conn, correction, collection, model)
            elif ctype == "ADD":
                removed, added = apply_add(conn, correction, collection, model)
            elif ctype == "ANNOTATE":
                removed, added = apply_annotate(conn, correction, collection, model)
            else:
                print(f"  ERROR: Unknown correction type '{ctype}' for {cid}")
                continue

            total_removed += len(removed)
            total_added += len(added)

        conn.commit()

    # Summary
    print(f"\n{'=' * 60}")
    print("Batch Complete")
    print(f"{'=' * 60}")
    print(f"Corrections applied: {len(corrections) - skipped}")
    print(f"Skipped (already applied): {skipped}")
    print(f"Facts superseded: {total_removed}")
    print(f"Corrected facts added: {total_added}")


# ---------------------------------------------------------------------------
# Interactive Mode
# ---------------------------------------------------------------------------

def run_interactive():
    """Interactive menu-driven correction tool."""
    print("=" * 60)
    print("Correction Propagation — Interactive Mode")
    print("=" * 60)

    with contextlib.closing(sqlite3.connect(DATABASE_FILE)) as conn:
        ensure_tables(conn)

        print("\nLoading ChromaDB and embedding model...")
        collection, model = get_chromadb_collection()

        while True:
            print("\n--- Correction Menu ---")
            print("1. Search facts by keyword")
            print("2. DELETE a fact (wrong, remove it)")
            print("3. REPLACE a fact (wrong, here's the right version)")
            print("4. REATTRIBUTE a fact (belongs to someone else)")
            print("5. ADD a missing fact")
            print("6. ANNOTATE a fact (add context/sentiment)")
            print("7. Show all corrections")
            print("0. Exit")

            choice = input("\nChoice: ").strip()

            if choice == "0":
                break
            elif choice == "1":
                keyword = input("Search keyword: ").strip()
                results = search_facts(conn, keyword)
                if not results:
                    print("  No active facts found.")
                else:
                    for i, r in enumerate(results):
                        print(f"  {i+1}. [{r['category']:<12} {r['confidence']:.1f}] {r['id'][:8]}... | {r['text'][:100]}")

            elif choice == "2":
                fact_id_prefix = input("Fact ID prefix to delete: ").strip()
                facts = find_facts_by_id_prefix(conn, fact_id_prefix)
                if not facts:
                    print("  No facts found with that prefix.")
                    continue
                for f in facts:
                    print(f"  Found: {f['text'][:100]}")
                confirm = input("  Delete? (y/n): ").strip().lower()
                if confirm == "y":
                    notes = input("  Reason: ").strip()
                    patterns_raw = input("  Block patterns (comma-separated keywords, or empty): ").strip()
                    patterns = [p.strip() for p in patterns_raw.split(",") if p.strip()] if patterns_raw else []

                    correction = {
                        "id": f"interactive-{str(uuid.uuid4())[:8]}",
                        "correction_type": "DELETE",
                        "original_fact_ids": [fact_id_prefix],
                        "original_fact_text": facts[0]["text"],
                        "match_patterns": patterns,
                        "notes": notes,
                    }
                    apply_delete(conn, correction, collection, model)
                    conn.commit()

            elif choice == "3":
                fact_id_prefix = input("Fact ID prefix to replace: ").strip()
                facts = find_facts_by_id_prefix(conn, fact_id_prefix)
                if not facts:
                    print("  No facts found with that prefix.")
                    continue
                for f in facts:
                    print(f"  Found: {f['text'][:100]}")
                corrected = input("  Corrected fact text: ").strip()
                category = input(f"  Category [{facts[0]['category']}]: ").strip() or facts[0]["category"]
                notes = input("  Reason: ").strip()
                patterns_raw = input("  Block patterns (comma-separated keywords, or empty): ").strip()
                patterns = [p.strip() for p in patterns_raw.split(",") if p.strip()] if patterns_raw else []

                correction = {
                    "id": f"interactive-{str(uuid.uuid4())[:8]}",
                    "correction_type": "REPLACE",
                    "original_fact_ids": [fact_id_prefix],
                    "original_fact_text": facts[0]["text"],
                    "corrected_fact_text": corrected,
                    "corrected_category": category,
                    "match_patterns": patterns,
                    "notes": notes,
                }
                apply_replace(conn, correction, collection, model)
                conn.commit()

            elif choice == "4":
                fact_id_prefix = input("Fact ID prefix to reattribute: ").strip()
                facts = find_facts_by_id_prefix(conn, fact_id_prefix)
                if not facts:
                    print("  No facts found with that prefix.")
                    continue
                for f in facts:
                    print(f"  Found: {f['text'][:100]}")
                subject = input("  Correct subject (e.g., spouse:Name, friend): ").strip()
                corrected = input("  Reattributed fact text (or empty to just delete): ").strip() or None
                notes = input("  Reason: ").strip()
                patterns_raw = input("  Block patterns (comma-separated keywords, or empty): ").strip()
                patterns = [p.strip() for p in patterns_raw.split(",") if p.strip()] if patterns_raw else []

                correction = {
                    "id": f"interactive-{str(uuid.uuid4())[:8]}",
                    "correction_type": "REATTRIBUTE",
                    "original_fact_ids": [fact_id_prefix],
                    "original_fact_text": facts[0]["text"],
                    "corrected_fact_text": corrected,
                    "corrected_category": "relationship",
                    "corrected_subject": subject,
                    "match_patterns": patterns,
                    "notes": notes,
                }
                apply_reattribute(conn, correction, collection, model)
                conn.commit()

            elif choice == "5":
                fact_text = input("  New fact text: ").strip()
                category = input("  Category: ").strip()
                notes = input("  Reason: ").strip()

                correction = {
                    "id": f"interactive-{str(uuid.uuid4())[:8]}",
                    "correction_type": "ADD",
                    "corrected_fact_text": fact_text,
                    "corrected_category": category,
                    "match_patterns": [],
                    "notes": notes,
                }
                apply_add(conn, correction, collection, model)
                conn.commit()

            elif choice == "6":
                fact_id_prefix = input("Fact ID prefix to annotate: ").strip()
                facts = find_facts_by_id_prefix(conn, fact_id_prefix)
                if not facts:
                    print("  No facts found with that prefix.")
                    continue
                for f in facts:
                    print(f"  Found: {f['text'][:100]}")
                annotation = input("  Annotation (e.g., sentiment:negative): ").strip()
                notes = input("  Reason: ").strip()

                correction = {
                    "id": f"interactive-{str(uuid.uuid4())[:8]}",
                    "correction_type": "ANNOTATE",
                    "original_fact_ids": [fact_id_prefix],
                    "original_fact_text": facts[0]["text"],
                    "annotation": annotation,
                    "match_patterns": [],
                    "notes": notes,
                }
                apply_annotate(conn, correction, collection, model)
                conn.commit()

            elif choice == "7":
                show_corrections(conn)
            else:
                print("  Invalid choice.")

    print("\nDone.")


# ---------------------------------------------------------------------------
# Show Corrections
# ---------------------------------------------------------------------------

def show_corrections(conn=None):
    """Display all stored corrections."""
    if conn is None:
        with contextlib.closing(sqlite3.connect(DATABASE_FILE)) as conn:
            return show_corrections(conn)

    rows = conn.execute("""
        SELECT id, correction_type, original_fact_text, corrected_fact_text, notes, created_at
        FROM user_corrections
        ORDER BY created_at
    """).fetchall()

    if not rows:
        print("\nNo corrections stored yet.")
    else:
        print(f"\n{'=' * 60}")
        print(f"Stored Corrections: {len(rows)}")
        print(f"{'=' * 60}")
        for r in rows:
            from datetime import datetime
            ts = datetime.fromtimestamp(r[5]).strftime("%Y-%m-%d %H:%M") if r[5] else "?"
            print(f"\n  [{r[1]:<12}] {r[0]} ({ts})")
            if r[2]:
                print(f"    Was: {r[2][:80]}")
            if r[3]:
                print(f"    Now: {r[3][:80]}")
            if r[4]:
                print(f"    Why: {r[4][:80]}")

    # Also show stats
    total = conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()[0]
    active = conn.execute("SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL").fetchone()[0]
    user_sourced = conn.execute(
        "SELECT COUNT(*) FROM memory_facts WHERE source = 'user_correction' AND superseded_by IS NULL"
    ).fetchone()[0]
    print(f"\n  Facts: {total} total, {active} active, {user_sourced} user-corrected")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Correction Propagation Tool (D-021)")
    parser.add_argument("--batch", type=str, help="Path to corrections JSON file")
    parser.add_argument("--interactive", action="store_true", help="Run interactive correction mode")
    parser.add_argument("--show", action="store_true", help="Show all stored corrections")

    args = parser.parse_args()

    if args.batch:
        run_batch(args.batch)
    elif args.interactive:
        run_interactive()
    elif args.show:
        with contextlib.closing(sqlite3.connect(DATABASE_FILE)) as conn:
            ensure_tables(conn)
            show_corrections(conn)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
