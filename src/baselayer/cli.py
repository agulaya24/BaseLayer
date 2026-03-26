#!/usr/bin/env python3
"""
Base Layer CLI — Personal AI Memory System

Pipeline (4 steps): Import -> Extract -> Author -> Compose

Usage:
    baselayer run <file> [-y]               One-command pipeline: import > extract > author > compose
    baselayer ui                            Local drag-and-drop web interface
    baselayer init                          Initialize a fresh database
    baselayer import <file> [--source X]    Import conversations (chatgpt/claude/journal)
    baselayer extract [--limit N]           Extract facts from conversations
    baselayer extract --identity-only       Extract identity traits from Claude Code sessions
    baselayer embed                         Generate vector embeddings (optional utility)
    baselayer author [--layer X]            Generate identity layers (requires Anthropic API key)
    baselayer compose                       Compose unified brief from deployed layers (Opus API)
    baselayer brief <message>               Assemble a memory brief for a message
    baselayer chat                          Interactive chat with memory-augmented Claude
    baselayer checkpoint <stage>            Quality gate reports (extraction/all)
    baselayer batch-extract --submit        Submit batch re-extraction (Anthropic Batch API, 50% cost)
    baselayer batch-extract --status        Check batch processing status
    baselayer batch-extract --process       Process completed batch results
    baselayer stats                         Show database statistics
    baselayer search <query>                Search facts by keyword or semantics
    baselayer review                        Review and correct facts interactively
    baselayer forget --fact ID              Soft-delete a specific fact by ID
    baselayer forget --conversation ID      Soft-delete all facts from a conversation
    baselayer forget --all                  Soft-delete ALL facts (requires confirmation)
    baselayer estimate                      Estimate API cost for extraction
    baselayer rebuild-fts                    Rebuild FTS5 full-text search index
"""

import contextlib
import sys
import io
import os
import argparse
from pathlib import Path

# Fix Windows encoding — prevent UnicodeEncodeError on cp1252 stdout
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")



def cmd_init(args):
    """Initialize a fresh Base Layer database."""
    import json
    from baselayer.config import PROJECT_ROOT, DATABASE_FILE

    # Create directory structure
    dirs = [
        PROJECT_ROOT / "data" / "database",
        PROJECT_ROOT / "data" / "vectors",
        PROJECT_ROOT / "data" / "raw",
        PROJECT_ROOT / "data" / "identity_layers",
        PROJECT_ROOT / "data" / "imports",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    if DATABASE_FILE.exists() and not args.force:
        print(f"Database already exists at {DATABASE_FILE}")
        print("Use --force to reinitialize (WARNING: deletes all data)")
        return

    # --- Privacy disclosure ---
    print()
    print("  Privacy Notice:")
    print("    Base Layer stores all data locally on your machine.")
    print("    During fact extraction, conversation text is sent to the Anthropic API")
    print("    (Claude Haiku) for processing. No data is stored by Anthropic.")
    print()
    print("    By continuing, you acknowledge this data processing.")
    try:
        consent = input("    Continue? [Y/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        consent = "n"
    if consent == "n":
        print("  Setup cancelled.")
        return
    print()

    # --- User name prompt ---
    try:
        name_input = input("  What name should the system use for you? ").strip()
    except (EOFError, KeyboardInterrupt):
        name_input = ""
    user_names = [name_input] if name_input else []

    # --- Pronoun prompt ---
    print()
    print("  Pronouns for identity layers (used in third-person descriptions):")
    print("    1. he/him")
    print("    2. she/her")
    print("    3. they/them")
    print("    4. Custom")
    try:
        pronoun_choice = input("  Select [1-4] (default: 3): ").strip()
    except (EOFError, KeyboardInterrupt):
        pronoun_choice = ""

    pronoun_map = {"1": "he/him", "2": "she/her", "3": "they/them"}
    if pronoun_choice in pronoun_map:
        user_pronouns = pronoun_map[pronoun_choice]
    elif pronoun_choice == "4":
        try:
            user_pronouns = input("  Enter custom pronouns: ").strip()
        except (EOFError, KeyboardInterrupt):
            user_pronouns = ""
        if not user_pronouns:
            user_pronouns = "they/them"
    else:
        user_pronouns = "they/them"
    print()

    # --- Write entity_map.json ---
    entity_map_path = PROJECT_ROOT / "data" / "entity_map.json"
    if entity_map_path.exists():
        with open(entity_map_path, "r", encoding="utf-8") as f:
            entity_map = json.load(f)
        entity_map["_user_names"] = user_names
        entity_map["_user_pronouns"] = user_pronouns
    else:
        entity_map = {
            "_user_names": user_names,
            "_user_pronouns": user_pronouns,
        }
    with open(entity_map_path, "w", encoding="utf-8") as f:
        json.dump(entity_map, f, indent=4)
    print(f"  Saved identity config to {entity_map_path}")

    import baselayer.init_database as init_database
    init_database.main()
    print(f"\nBase Layer initialized at {PROJECT_ROOT}")
    print(f"Database: {DATABASE_FILE}")
    print(f"\nNext steps:")
    print(f"  Option A: Import existing conversations")
    print(f"    baselayer import <your-chatgpt-export.zip>")
    print(f"  Option B: Start from scratch with journal prompts")
    print(f"    baselayer journal")
    print(f"\n  Journal entries produce the highest-quality identity data.")
    print(f"  You can do both — import conversations AND journal.")


def cmd_import(args):
    """Import conversation history or text files."""
    import baselayer.import_conversations as import_conversations

    file_path = args.file
    if not Path(file_path).exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    source = args.source
    if not source:
        # Auto-detect source from file extension and name
        p = Path(file_path)
        name = p.name.lower()
        if p.is_dir() or p.suffix.lower() in (".txt", ".md", ".docx"):
            source = "text"
        elif "chatgpt" in name or name.endswith(".zip"):
            source = "chatgpt"
        elif "claude" in name:
            source = "claude_web"
        elif "journal" in name:
            source = "journal"
        elif p.suffix.lower() == ".json":
            source = "json"
        else:
            source = "chatgpt"  # Default
        print(f"Auto-detected source: {source}")

    if source == "text":
        sys.argv = ["import_conversations.py", "--text", file_path]
    elif source == "json":
        sys.argv = ["import_conversations.py", "--json", file_path]
    else:
        sys.argv = ["import_conversations.py", f"--{source.replace('_', '-')}", file_path]
    import_conversations.main()


def cmd_estimate(args):
    """Estimate API cost for extraction based on imported data."""
    from baselayer.config import DATABASE_FILE, EXTRACTION_API_MODEL, get_db

    if not DATABASE_FILE.exists():
        print("No database found. Run: baselayer init")
        sys.exit(1)

    with contextlib.closing(get_db()) as conn:
        # Count conversations awaiting extraction
        total_convos = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        extracted = conn.execute("SELECT COUNT(DISTINCT conversation_id) FROM extraction_log").fetchone()[0]
        pending = total_convos - extracted

        # Estimate tokens from message content
        total_chars = conn.execute("""
            SELECT COALESCE(SUM(LENGTH(content_text)), 0)
            FROM messages m
            JOIN conversations c ON m.conversation_id = c.id
            WHERE c.id NOT IN (SELECT conversation_id FROM extraction_log)
        """).fetchone()[0]

        # Token estimation (4 chars per token)
        input_tokens = total_chars // 4
        # Output estimate: ~200 tokens per conversation (JSON facts)
        output_tokens = pending * 200

        # Pricing per 1M tokens (as of 2026)
        pricing = {
            "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00, "name": "Haiku 4.5"},
            "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00, "name": "Sonnet 4"},
            "claude-opus-4-20250514": {"input": 15.00, "output": 75.00, "name": "Opus 4"},
        }

        print(f"\n  Extraction Cost Estimate")
        print(f"  {'='*45}")
        print(f"  Total conversations:    {total_convos:,}")
        print(f"  Already extracted:      {extracted:,}")
        print(f"  Pending extraction:     {pending:,}")
        print(f"  Estimated input tokens: {input_tokens:,}")
        print(f"  Estimated output tokens:{output_tokens:,}")

        print(f"\n  Estimated cost by model:")
        for model_id, info in pricing.items():
            input_cost = (input_tokens / 1_000_000) * info["input"]
            output_cost = (output_tokens / 1_000_000) * info["output"]
            total_cost = input_cost + output_cost
            marker = " <-- current default" if model_id == EXTRACTION_API_MODEL else ""
            print(f"    {info['name']:12s} ${total_cost:>7.2f}{marker}")

        print(f"\n  Note: Actual cost depends on conversation length and")
        print(f"  fact density. Estimates are typically within 2x of actual.")

        # Also show downstream pipeline costs
        if pending > 0:
            print(f"\n  Post-extraction pipeline costs (one-time):")
            print(f"    Layer authoring (Sonnet): ~$0.10")
            print(f"    Brief composition (Opus): ~$0.20")
            print(f"    Total pipeline:           ~$0.30")

        print()


def cmd_extract(args):
    """Extract facts from imported conversations."""
    from baselayer import config

    # Privacy reminder for API extraction
    print("  Note: Extraction sends conversation text to the Anthropic API for processing.")

    # Override backend if specified
    if args.backend:
        config.EXTRACTION_BACKEND = args.backend

    if config.EXTRACTION_BACKEND == "anthropic":
        _check_api_key()
        print(f"Using Anthropic API ({config.EXTRACTION_API_MODEL}) for extraction")
    else:
        print(f"Using local Ollama ({config.LLM_MODEL}) for extraction")

    if args.identity_only:
        print("Mode: IDENTITY-ONLY — extracting personal traits from project conversations")

    import baselayer.extract_facts as extract_facts

    argv = ["extract_facts.py"]
    if args.limit:
        argv.extend(["--limit", str(args.limit)])
    if args.identity_only:
        argv.append("--identity-only")
    if args.source:
        argv.extend(["--source", args.source])
    if getattr(args, 'document_mode', False):
        argv.append("--document-mode")
    sys.argv = argv
    extract_facts.main()


def cmd_embed(args):
    """Generate vector embeddings for facts and messages.

    NOTE: embed.py is an optional utility from the pre-simplified pipeline.
    It is no longer part of the default 4-step pipeline (Import -> Extract -> Author -> Compose).
    Run directly: python scripts/embed.py
    """
    import baselayer.embed as embed
    sys.argv = ["embed.py"]
    embed.main()



def cmd_author(args):
    """Generate identity layers (ANCHORS, CORE, PREDICTIONS)."""
    _check_api_key()
    _check_extraction_complete()
    _check_fact_floor()

    import baselayer.author_layers as author_layers

    argv = ["author_layers.py", "--generate"]
    if args.layer:
        argv.append(args.layer)
    else:
        argv.append("all")
    if getattr(args, 'no_citations', False):
        argv.append("--no-citations")
    sys.argv = argv
    author_layers.main()

    # Check if any layers were actually generated
    from baselayer.config import ANCHORS_LAYER_FILE, CORE_LAYER_FILE, PREDICTIONS_LAYER_FILE
    layers_exist = any(f.exists() for f in [ANCHORS_LAYER_FILE, CORE_LAYER_FILE, PREDICTIONS_LAYER_FILE])
    if not layers_exist:
        print("\nNo layers were generated. Your dataset may not have enough identity-tier facts yet.")
        print("Run: baselayer stats")
        return

    # Chain compose step if requested
    if getattr(args, 'compose', False):
        print(f"\n{'='*60}")
        print(f"  Chaining unified brief composition...")
        cmd_compose(args)


def cmd_compose(args):
    """Compose a unified narrative brief from deployed identity layers."""
    _check_api_key()
    _check_extraction_complete()
    _check_fact_floor()
    from baselayer.agent_pipeline import compose_unified_brief
    brief = compose_unified_brief()
    if brief:
        print(f"\n  Unified brief composed successfully.")
        print(f"  Length: {len(brief)} chars, ~{len(brief) // 4} tokens")
    else:
        print(f"\n  Composition failed. Check that layers are deployed.")
        sys.exit(1)


def cmd_brief(args):
    """Assemble a memory brief for a message."""
    import baselayer.assemble_brief as assemble_brief
    sys.argv = ["assemble_brief.py", "--show-brief", args.message]
    assemble_brief.main()


def cmd_chat(args):
    """Interactive chat with memory-augmented Claude."""
    _check_api_key()
    import baselayer.assemble_brief as assemble_brief
    sys.argv = ["assemble_brief.py", "--interactive"]
    assemble_brief.main()


def cmd_checkpoint(args):
    """Run pipeline quality checkpoint reports."""
    from baselayer.checkpoint import run_checkpoint
    run_checkpoint(args.stage)



def cmd_stats(args):
    """Show database statistics."""
    from baselayer.config import DATABASE_FILE, get_db

    if not DATABASE_FILE.exists():
        print("No database found. Run: baselayer init")
        sys.exit(1)

    with contextlib.closing(get_db()) as conn:
        convos = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        messages = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        facts = conn.execute("SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL").fetchone()[0]
        superseded = conn.execute("SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NOT NULL").fetchone()[0]

        # Tier breakdown
        tiers = conn.execute("""
            SELECT knowledge_tier, COUNT(*) as cnt
            FROM memory_facts WHERE superseded_by IS NULL
            GROUP BY knowledge_tier ORDER BY cnt DESC
        """).fetchall()

        # Sources
        sources = conn.execute("""
            SELECT source, COUNT(*) as cnt
            FROM conversations GROUP BY source ORDER BY cnt DESC
        """).fetchall()

        print(f"\n  Base Layer Database Statistics")
        print(f"  {'='*40}")
        print(f"  Conversations:  {convos:,}")
        print(f"  Messages:       {messages:,}")
        print(f"  Active facts:   {facts:,}")
        print(f"  Superseded:     {superseded:,}")

        if tiers:
            print(f"\n  Knowledge Tiers:")
            for t in tiers:
                tier_name = t["knowledge_tier"] or "unclassified"
                print(f"    {tier_name:15s} {t['cnt']:,}")

        if sources:
            print(f"\n  Sources:")
            for s in sources:
                print(f"    {s['source']:15s} {s['cnt']:,}")

        print()


def cmd_search(args):
    """Search facts by keyword or semantic similarity."""
    import baselayer.semantic_search as semantic_search
    sys.argv = ["semantic_search.py", args.query]
    semantic_search.main()


def _delete_vectors(fact_ids):
    """Delete fact vectors from ChromaDB. Returns count of vectors removed."""
    from baselayer.config import VECTORS_DIR

    if not fact_ids:
        return 0

    try:
        import chromadb
    except ImportError:
        print("  WARNING: chromadb not available. Skipping vector cleanup.")
        return 0

    try:
        client = chromadb.PersistentClient(path=str(VECTORS_DIR))
        collection = client.get_collection("memory_facts")
    except Exception as e:
        # Collection doesn't exist — nothing to delete
        print(f"WARNING: Could not access memory_facts collection: {e}", file=sys.stderr)
        return 0

    # ChromaDB delete only works with IDs that exist — filter first
    existing = set()
    for fid in fact_ids:
        try:
            result = collection.get(ids=[fid])
            if result and result["ids"]:
                existing.add(fid)
        except Exception:
            pass

    if existing:
        collection.delete(ids=list(existing))

    return len(existing)


def cmd_forget(args):
    """Soft-delete facts by ID, conversation, or all. Removes corresponding vectors."""
    import time
    from baselayer.config import DATABASE_FILE, get_db

    if not DATABASE_FILE.exists():
        print("No database found. Run: baselayer init")
        sys.exit(1)

    # Determine mode
    if args.all:
        mode = "all"
    elif args.fact:
        mode = "fact"
    elif args.conversation:
        mode = "conversation"
    else:
        print("Specify one of: --fact ID, --conversation ID, or --all")
        sys.exit(1)

    with contextlib.closing(get_db()) as conn:

        if mode == "fact":
            # Single fact by ID
            row = conn.execute(
                "SELECT id, fact_text FROM memory_facts WHERE id = ? AND superseded_by IS NULL",
                (args.fact,)
            ).fetchone()
            if not row:
                print(f"No active fact found with ID: {args.fact}")
                return
            fact_ids = [row["id"]]
            print(f"\n  Fact: {row['fact_text'][:120]}")
            print(f"  ID:   {row['id']}")

        elif mode == "conversation":
            rows = conn.execute(
                "SELECT id, fact_text FROM memory_facts"
                " WHERE source_conversation_id = ? AND superseded_by IS NULL",
                (args.conversation,)
            ).fetchall()
            if not rows:
                print(f"No active facts found for conversation: {args.conversation}")
                return
            fact_ids = [r["id"] for r in rows]
            print(f"\n  Found {len(rows)} active facts from conversation {args.conversation}")

        elif mode == "all":
            rows = conn.execute(
                "SELECT id FROM memory_facts WHERE superseded_by IS NULL"
            ).fetchall()
            if not rows:
                print("No active facts to delete.")
                return
            fact_ids = [r["id"] for r in rows]
            print(f"\n  This will soft-delete ALL {len(rows)} active facts.")
            try:
                confirm = input("  Type DELETE to confirm: ").strip()
            except (EOFError, KeyboardInterrupt):
                confirm = ""
            if confirm != "DELETE":
                print("  Cancelled.")
                return

        # Soft-delete in SQLite
        now = time.time()
        with conn:
            for fid in fact_ids:
                conn.execute(
                    "UPDATE memory_facts SET superseded_by = 'user_forget', updated_at = ?"
                    " WHERE id = ? AND superseded_by IS NULL",
                    (now, fid),
                )

        # Delete vectors from ChromaDB
        vectors_removed = _delete_vectors(fact_ids)

        print(f"\n  Soft-deleted {len(fact_ids)} fact(s).")
        print(f"  Removed {vectors_removed} vector(s) from ChromaDB.")
        print(f"  Facts are hidden but not permanently deleted.")
        print(f"  They can be recovered by clearing the superseded_by field.")


def cmd_provenance(args):
    """Show provenance chain for identity layer claims."""
    from baselayer.config import DATABASE_FILE, get_db

    if not DATABASE_FILE.exists():
        print("No database found. Run: baselayer init")
        sys.exit(1)

    with contextlib.closing(get_db()) as conn:
        # Check if provenance table exists
        table_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='layer_claim_provenance'"
        ).fetchone()

        if not table_exists:
            print("No provenance data found. Run: baselayer author (provenance is captured at authoring time)")
            return

        if args.claim:
            # Trace a specific claim
            rows = conn.execute("""
                SELECT p.claim_id, p.claim_text, p.fact_id, p.link_method,
                       p.rank_in_claim, p.layer_name, p.layer_version,
                       f.fact_text, f.fact_type, f.knowledge_tier,
                       f.recurrence_count, f.source_conversation_id
                FROM layer_claim_provenance p
                LEFT JOIN memory_facts f ON p.fact_id = f.id
                WHERE UPPER(p.claim_id) = UPPER(?)
                ORDER BY p.rank_in_claim
            """, (args.claim,)).fetchall()

            if not rows:
                print(f"No provenance found for claim '{args.claim}'")
                return

            first = rows[0]
            print(f"\n  Claim: {first['claim_id']} — {first['claim_text'] or '(unnamed)'}")
            print(f"  Layer: {first['layer_name']} ({first['layer_version'] or 'unknown'})")
            print(f"\n  Supporting Facts ({len(rows)}):")

            for r in rows:
                fact_text = r["fact_text"] or "(fact not found in DB)"
                tier = r["knowledge_tier"] or "?"
                rec = r["recurrence_count"] or 0
                print(f"    [{r['rank_in_claim']}] {fact_text[:150]}")
                print(f"        tier: {tier}, recurrence: {rec}, linked via: {r['link_method']}")

                if r["source_conversation_id"]:
                    conv = conn.execute(
                        "SELECT title FROM conversations WHERE id = ?",
                        (r["source_conversation_id"],)
                    ).fetchone()
                    if conv and conv["title"]:
                        print(f"        source: \"{conv['title'][:80]}\"")

        else:
            # Summary mode — show all claims with fact counts
            rows = conn.execute("""
                SELECT layer_name, claim_id, claim_text, COUNT(*) as fact_count,
                       layer_version
                FROM layer_claim_provenance
                GROUP BY layer_name, claim_id
                ORDER BY layer_name,
                  CASE SUBSTR(claim_id, 1, 1)
                    WHEN 'A' THEN 1 WHEN 'M' THEN 2
                    WHEN 'C' THEN 3 WHEN 'P' THEN 4
                    ELSE 5
                  END,
                  CAST(SUBSTR(claim_id, 2) AS INTEGER)
            """).fetchall()

            if not rows:
                print("No provenance entries found.")
                return

            total_facts = sum(r["fact_count"] for r in rows)
            print(f"\n  Provenance Summary ({len(rows)} claims, {total_facts} fact links)")
            print()

            current_layer = None
            for r in rows:
                if r["layer_name"] != current_layer:
                    current_layer = r["layer_name"]
                    print(f"  {current_layer} ({r['layer_version'] or '?'}):")
                claim_text = r["claim_text"] or "(unnamed)"
                print(f"    {r['claim_id']:4s} {claim_text[:60]:60s} ({r['fact_count']} facts)")

            print(f"\n  Use: baselayer provenance --claim A1  (to trace a specific claim)")


def cmd_verify(args):
    """Verify identity layer provenance (vector similarity + claim checks)."""
    from baselayer.config import DATABASE_FILE

    if not DATABASE_FILE.exists():
        print("No database found. Run: baselayer init")
        sys.exit(1)

    from baselayer.verify_provenance import (
        vector_audit,
        run_verification,
        run_full_verification,
        run_nli_verification,
        format_vector_results,
        format_claim_results,
        format_coverage_results,
        format_nli_results,
        _check_coverage,
    )

    layer = (args.layer or "all").upper()

    print(f"\n  Base Layer Provenance Verification")
    print(f"  {'=' * 50}")

    if args.generate:
        # Generate vector provenance from scratch (S68)
        from baselayer.verify_provenance import generate_vector_provenance
        if layer == "ALL":
            layers = ["ANCHORS", "CORE", "PREDICTIONS"]
        else:
            layers = [layer]

        for lname in layers:
            print(f"\n  Generating vector provenance for {lname}...")
            results = generate_vector_provenance(lname)
            if not results:
                print(f"  No provenance generated for {lname}")
        return

    elif args.nli:
        # NLI-only mode (DeBERTa entailment check)
        print(f"\n  Running NLI entailment verification...")
        nli_results = run_nli_verification(layer, claim_id_filter=args.claim)
        print(format_nli_results(nli_results))

    elif args.vector:
        # Vector audit only (topic proximity check)
        # S6: pass claim_id_filter so --vector --claim A1 works consistently
        if layer == "ALL":
            layers = ["ANCHORS", "CORE", "PREDICTIONS"]
        else:
            layers = [layer]

        vector_results = {}
        for lname in layers:
            print(f"\n  Running vector audit for {lname}...")
            vr = vector_audit(lname, claim_id_filter=args.claim)
            if vr:
                vector_results[lname] = vr

        if vector_results:
            print(format_vector_results(vector_results))
        else:
            print("  No vector results (no provenance citations or embeddings found)")

    elif args.claims:
        # S9: Claims-only mode (skip vector audit)
        print(f"\n  Running claim verification only (--claims mode)...")
        summary = run_verification(layer, claim_id_filter=args.claim)
        print(format_claim_results(summary))

        # Include coverage when not filtering to a single claim
        if not args.claim:
            coverage = _check_coverage(
                layer if layer != "ALL" else None
            )
            print(format_coverage_results(coverage))

    elif args.claim:
        # Specific claim verification
        print(f"\n  Verifying claim: {args.claim}")
        summary = run_verification(layer, claim_id_filter=args.claim)
        print(format_claim_results(summary))

    else:
        # Full verification (vector + claims)
        result = run_full_verification(layer, claim_id_filter=None)

        if result["vector"]:
            print(format_vector_results(result["vector"]))

        print(format_claim_results(result["claims"]))

        # Coverage (C11)
        if result.get("coverage"):
            print(format_coverage_results(result["coverage"]))

    print()


def cmd_review(args):
    """Interactive fact review — inspect, approve, or flag facts."""
    from baselayer.config import DATABASE_FILE, get_db

    if not DATABASE_FILE.exists():
        print("No database found. Run: baselayer init")
        sys.exit(1)

    with contextlib.closing(get_db()) as conn:
        # Determine what to review
        tier_filter = args.tier
        limit = args.limit or 50

        conditions = ["superseded_by IS NULL"]
        params = []

        if tier_filter:
            conditions.append("knowledge_tier = ?")
            params.append(tier_filter)

        # Safety: WHERE clause is built from a fixed set of parameterized conditions,
        # not from user input. All dynamic values go through ? placeholders.
        where = " AND ".join(conditions)
        params.append(limit)

        rows = conn.execute(
            "SELECT id, fact_text, category, knowledge_tier, fact_type,"
            "       commitment_depth, recurrence_count, significance_score"
            " FROM memory_facts"
            " WHERE " + where +
            " ORDER BY"
            "   CASE knowledge_tier"
            "     WHEN 'identity' THEN 1"
            "     WHEN 'situational' THEN 2"
            "     WHEN 'context' THEN 3"
            "     ELSE 4"
            "   END,"
            "   significance_score DESC"
            " LIMIT ?",
            params
        ).fetchall()

        if not rows:
            print("No facts to review.")
            return

        print(f"\n  Base Layer Fact Review")
        print(f"  {'='*50}")
        print(f"  Showing {len(rows)} facts{f' (tier: {tier_filter})' if tier_filter else ''}")
        print(f"  Commands: [enter]=next, d=delete, f=flag, q=quit\n")

        deleted = 0
        flagged = 0
        reviewed = 0

        for i, r in enumerate(rows):
            tier = r["knowledge_tier"] or "?"
            ftype = r["fact_type"] or "?"
            depth = r["commitment_depth"] or "?"
            cat = r["category"] or "?"
            rec = r["recurrence_count"] or 0
            sig = r["significance_score"] or 0

            print(f"  [{i+1}/{len(rows)}] {r['fact_text']}")
            print(f"    tier={tier}  type={ftype}  depth={depth}  cat={cat}  rec={rec}  sig={sig:.1f}")

            try:
                action = input("    > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n  Quitting.")
                break

            if action == "q":
                break
            elif action == "d":
                import time
                with conn:
                    conn.execute("""
                        UPDATE memory_facts
                        SET superseded_by = 'user_review', updated_at = ?
                        WHERE id = ?
                    """, (time.time(), r["id"]))
                deleted += 1
                print("    Deleted.")
            elif action == "f":
                note = input("    Flag note: ").strip()
                with conn:
                    conn.execute("""
                        INSERT OR REPLACE INTO user_corrections
                        (id, correction_type, original_fact_id, original_fact_text,
                         annotation, created_at)
                        VALUES (?, 'flag', ?, ?, ?, ?)
                    """, (r["id"] + "_flag", r["id"], r["fact_text"], note, time.time()))
                flagged += 1
                print("    Flagged.")
            else:
                reviewed += 1

            print()

        print(f"\n  Review complete: {reviewed} kept, {deleted} deleted, {flagged} flagged")


def cmd_journal(args):
    """Guided journal prompts for fast identity building (cold start)."""
    import time
    import uuid
    from baselayer.config import DATABASE_FILE, get_db

    if not DATABASE_FILE.exists():
        print("No database found. Run: baselayer init")
        sys.exit(1)

    # Journal prompts designed to elicit identity-rich responses.
    # Order matters: start broad, go deep, end with forward-looking.
    JOURNAL_PROMPTS = [
        {
            "id": "who",
            "prompt": "Describe yourself in a few sentences — who are you, what do you do, and what matters most to you?",
            "category": "identity",
        },
        {
            "id": "relationships",
            "prompt": "Who are the most important people in your life? What role does each play?",
            "category": "relationships",
        },
        {
            "id": "values",
            "prompt": "What do you believe strongly that most people would disagree with? What principles guide your decisions?",
            "category": "values",
        },
        {
            "id": "work",
            "prompt": "What are you building or working on right now? What's your professional background?",
            "category": "career",
        },
        {
            "id": "patterns",
            "prompt": "What are your recurring struggles or bad habits? When do you tend to fail, and how do you recover?",
            "category": "behavioral",
        },
        {
            "id": "interests",
            "prompt": "What do you spend your time on outside of work? What are your hobbies, passions, or obsessions?",
            "category": "interests",
        },
        {
            "id": "formative",
            "prompt": "What's a defining experience that shaped who you are today? Something that fundamentally changed how you see the world?",
            "category": "formative",
        },
        {
            "id": "future",
            "prompt": "Where are you headed? What are you trying to become or achieve in the next few years?",
            "category": "goals",
        },
    ]

    with contextlib.closing(get_db()) as conn:
        print(f"\n  Base Layer Journal — Identity Onboarding")
        print(f"  {'='*50}")
        print(f"  Answer these questions to quickly build your identity profile.")
        print(f"  Write naturally — more detail means better identity quality.")
        print(f"  Press enter to skip a question, type 'quit' to stop.\n")

        entries = []
        for i, jp in enumerate(JOURNAL_PROMPTS):
            print(f"  [{i+1}/{len(JOURNAL_PROMPTS)}] {jp['prompt']}")
            print()

            lines = []
            print("  (Type your response. Enter a blank line when done.)")
            while True:
                try:
                    line = input("  > ")
                except (EOFError, KeyboardInterrupt):
                    print("\n  Quitting.")
                    break
                if line.strip().lower() == "quit":
                    break
                if line.strip() == "" and lines:
                    break
                if line.strip() == "" and not lines:
                    # Skip this prompt
                    break
                lines.append(line)

            if lines:
                text = "\n".join(lines)
                entries.append({"id": jp["id"], "category": jp["category"], "text": text})
                print(f"    Saved ({len(text)} chars)\n")
            else:
                print(f"    Skipped\n")

            if line.strip().lower() == "quit":
                break

        if not entries:
            print("  No entries written. Come back anytime: baselayer journal")
            return

        # Store as a journal conversation
        now = time.time()
        conv_id = f"journal_{int(now)}"
        with conn:
            conn.execute("""
                INSERT INTO conversations (id, title, created_at, updated_at, message_count, source)
                VALUES (?, ?, ?, ?, ?, 'journal')
            """, (conv_id, "Identity Journal", now, now, len(entries)))

            for i, entry in enumerate(entries):
                msg_id = str(uuid.uuid4())
                # Store as user message with category prefix for extraction
                tagged_text = f"[{entry['category']}] {entry['text']}"
                conn.execute("""
                    INSERT INTO messages (id, conversation_id, role, content_text, content_type,
                                          sequence_order, created_at)
                    VALUES (?, ?, 'user', ?, 'text', ?, ?)
                """, (msg_id, conv_id, tagged_text, i, now))

        print(f"\n  {'='*50}")
        print(f"  Saved {len(entries)} journal entries as conversation '{conv_id}'")
        print(f"\n  Next steps:")
        print(f"    1. Extract facts:  baselayer extract")
        print(f"    2. Author layers:  baselayer author")
        print(f"    3. Compose brief:  baselayer compose")
        print(f"    4. Start MCP:      baselayer-mcp")
        print(f"\n  Tip: Journal entries are the highest quality input for identity.")
        print(f"  Run 'baselayer journal' again anytime to add more.\n")


def _run_traceability():
    """Post-compose traceability: tier facts, generate embeddings, build provenance, detect tensions.

    These steps don't change the identity model output — they build the audit trail
    that makes every claim inspectable. Cost: ~$0.05 per subject (Haiku for tensions).
    """
    import sqlite3
    from baselayer.config import DATABASE_FILE, VECTORS_DIR, PROJECT_ROOT

    if not DATABASE_FILE.exists():
        print("  No database found, skipping traceability.")
        return

    conn = sqlite3.connect(str(DATABASE_FILE))

    # 5a: Rule-based tiering (predicate -> knowledge_tier)
    print("  5a. Tiering facts by predicate...")
    IDENTITY_PREDS = (
        'values', 'believes', 'fears', 'identifies_as', 'aspires_to',
        'prioritizes', 'avoids', 'practices', 'excels_at', 'struggles_with',
        'loves', 'hates', 'enjoys', 'dislikes', 'builds', 'founded',
        'decides', 'decided', 'experienced', 'lost', 'follows', 'monitors',
        'plays', 'trades', 'maintains', 'prefers',
    )
    placeholders = ','.join(f"'{p}'" for p in IDENTITY_PREDS)
    id_count = conn.execute(f"""
        UPDATE memory_facts SET knowledge_tier = 'identity'
        WHERE (knowledge_tier IS NULL OR knowledge_tier = 'untiered')
        AND predicate IN ({placeholders})
    """).rowcount
    ctx_count = conn.execute("""
        UPDATE memory_facts SET knowledge_tier = 'contextual'
        WHERE knowledge_tier IS NULL OR knowledge_tier = 'untiered'
    """).rowcount
    conn.commit()
    print(f"      {id_count} -> identity, {ctx_count} -> contextual")

    # 5b: Embed facts into ChromaDB (if not already done)
    print("  5b. Checking embeddings...")
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(VECTORS_DIR))
        try:
            collection = client.get_collection("memory_facts")
            db_count = conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()[0]
            vec_count = collection.count()
            if vec_count >= db_count * 0.9:
                print(f"      {vec_count}/{db_count} facts already embedded. Skipping.")
            else:
                print(f"      {vec_count}/{db_count} embedded. Running embed...")
                conn.close()
                cmd_embed(type('', (), {'batch_size': 64})())
                conn = sqlite3.connect(str(DATABASE_FILE))
        except Exception:
            print(f"      No collection found. Running embed...")
            conn.close()
            cmd_embed(type('', (), {'batch_size': 64})())
            conn = sqlite3.connect(str(DATABASE_FILE))
    except ImportError:
        print("      chromadb not installed, skipping embeddings.")

    # 5c: Vector provenance (embedding similarity traces for each layer claim)
    print("  5c. Generating vector provenance...")
    try:
        from sentence_transformers import SentenceTransformer
        from baselayer.config import EMBEDDING_MODEL
        import baselayer.api_client as ac
        if ac._embedding_model is None:
            ac._embedding_model = SentenceTransformer(EMBEDDING_MODEL)

        from baselayer.verify_provenance import generate_vector_provenance, _reset_chroma_cache
        _reset_chroma_cache()

        total_links = 0
        for layer in ["ANCHORS", "CORE", "PREDICTIONS"]:
            results = generate_vector_provenance(layer)
            links = sum(len(r.get("fact_ids", [])) for r in results)
            total_links += links
            print(f"      {layer}: {len(results)} claims, {links} fact links")
        print(f"      Total: {total_links} provenance links")
    except ImportError as e:
        print(f"      sentence_transformers not available: {e}")
    except Exception as e:
        print(f"      Provenance error: {e}")

    # 5d: Tension detection (embedding pairs + Haiku classification)
    print("  5d. Detecting tensions...")
    try:
        import sys as _sys
        import baselayer.config as _cfg
        _sys.modules['config'] = _cfg
        import baselayer.api_client as _ac
        _sys.modules['api_client'] = _ac

        _archive = str(Path(__file__).parent / "archive" / "utilities")
        if _archive not in _sys.path:
            _sys.path.insert(0, _archive)

        import detect_contradictions as dc
        from baselayer.config import get_db
        import contextlib

        with contextlib.closing(get_db()) as tconn:
            facts = dc.load_facts(tconn)
            if len(facts) >= 2:
                embeddings = dc.embed_facts(facts)
                candidates = dc.find_candidate_pairs(facts, embeddings, threshold=0.45)
                max_pairs = min(len(candidates), 30)
                tensions_found = 0
                for pair in candidates[:max_pairs]:
                    fa, fb = pair["fact_a"], pair["fact_b"]
                    result = dc.classify_pair_haiku(
                        fa["fact_text"], fb["fact_text"],
                        fa.get("predicate", "unknown"), fb.get("predicate", "unknown")
                    )
                    if result.get("verdict") in ("CONTRADICTION", "TENSION"):
                        tensions_found += 1
                print(f"      {tensions_found} tensions found from {max_pairs} candidates")
            else:
                print(f"      Too few facts ({len(facts)}) for tension detection")
    except ImportError as e:
        print(f"      Tension detection unavailable: {e}")
    except Exception as e:
        print(f"      Tension error: {e}")

    conn.close()
    print("  Traceability complete.\n")


def cmd_pipeline(args):
    """S98 Phase 4: Unified pipeline — one command, all gates enforced.

    Usage:
        baselayer pipeline <subject_id>          # V1: fresh run
        baselayer pipeline <subject_id> --v2     # V2: re-extract with expanded corpus
    """
    import sqlite3 as _sql

    subject_id = args.subject_id
    v2_mode = getattr(args, 'v2', False)

    _check_api_key()
    _check_pipeline_lock()

    # Resolve subject from registry
    from baselayer.config import DATABASE_FILE
    main_db = DATABASE_FILE
    if not main_db.exists():
        print("Error: No database. Run 'baselayer init' first.")
        sys.exit(1)

    conn = _sql.connect(str(main_db))
    conn.row_factory = _sql.Row
    subject = conn.execute("SELECT * FROM subjects WHERE id = ?", (subject_id,)).fetchone()
    conn.close()

    if not subject:
        print(f"Error: Subject '{subject_id}' not found in registry.")
        print(f"Run 'baselayer subject list' to see available subjects.")
        sys.exit(1)

    env_dir = subject["environment_dir"]
    source_dir_name = subject["source_dir"]
    doc_mode = bool(subject["document_mode"])
    name = subject["name"]

    # Resolve paths
    from baselayer.seed_industry import ANTHROPIC_ROOT
    memory_dir = ANTHROPIC_ROOT / "subjects" / env_dir
    if not memory_dir.exists():
        memory_dir = ANTHROPIC_ROOT / env_dir

    # Find source directory
    source_dir = None
    if source_dir_name:
        source_dir = ANTHROPIC_ROOT / "memory_system" / "data" / source_dir_name
    else:
        # Try common patterns
        for pattern in [f"{subject_id}_source", f"{subject_id.replace('_', '_')}_source"]:
            candidate = ANTHROPIC_ROOT / "memory_system" / "data" / pattern
            if candidate.exists():
                source_dir = candidate
                break

    print(f"\n{'='*60}")
    print(f"  Base Layer Pipeline — {name}")
    print(f"  Mode: {'V2 (re-extract)' if v2_mode else 'V1 (fresh)'}")
    print(f"  Memory: {memory_dir}")
    print(f"  Source: {source_dir or 'N/A'}")
    print(f"  Document mode: {'Yes' if doc_mode else 'No'}")
    print(f"{'='*60}\n")

    if not memory_dir.exists():
        print(f"Error: Memory directory not found: {memory_dir}")
        sys.exit(1)

    # V2: Check manifest + snapshot + clear
    if v2_mode:
        if source_dir:
            _check_manifest(subject_id, str(source_dir))

        print(f"  V2 mode: Creating snapshot before clearing...")
        _snapshot_before_clear(memory_dir=str(memory_dir))

        # Clear extraction data (both SQLite + ChromaDB per S65)
        os.environ["MEMORY_SYSTEM_ROOT"] = str(memory_dir)
        from baselayer.config import DATABASE_FILE as SUBJ_DB
        # Re-resolve after env change
        from importlib import reload
        import baselayer.config as _cfg
        reload(_cfg)

        import baselayer.extract_facts as ef
        sys.argv = ["extract_facts.py", "--reset"]
        ef.main()
        print(f"  V2: Extraction data cleared.")

    # Set environment for this subject
    os.environ["MEMORY_SYSTEM_ROOT"] = str(memory_dir)
    from importlib import reload
    import baselayer.config as _cfg
    reload(_cfg)

    # Init DB if needed
    from baselayer.config import DATABASE_FILE as SUBJ_DB_FILE
    if not SUBJ_DB_FILE.exists():
        print(f"  Initializing database...")
        from baselayer.init_database import init_database
        init_database(SUBJ_DB_FILE)

    # Step 1: Import
    _conn = _sql.connect(str(SUBJ_DB_FILE))
    _existing = _conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
    _conn.close()

    if _existing > 0 and not v2_mode:
        print(f"  {_existing} conversations already imported. Skipping import.")
    elif source_dir and source_dir.exists():
        print(f"\n  Step 1: Importing from {source_dir.name}...")
        # Create a minimal args object for cmd_import
        class _ImportArgs:
            file = str(source_dir)
            source = "text"
            document_mode = doc_mode
            subject = name
            force = False
        cmd_import(_ImportArgs())
    else:
        print(f"  No source directory — skipping import.")

    # Step 2: Extract (batch if available, sequential fallback)
    print(f"\n  Step 2: Extracting facts...")
    import baselayer.extract_facts as extract_facts
    argv = ["extract_facts.py"]
    if doc_mode:
        argv.append("--document-mode")
    sys.argv = argv
    extract_facts.main()

    # Gates before authoring
    print(f"\n  Checking gates...")
    _check_extraction_complete()
    _check_fact_floor()

    # Step 3: Author layers
    print(f"\n  Step 3: Authoring identity layers...")
    import baselayer.author_layers as author_layers
    sys.argv = ["author_layers.py", "--generate", "all"]
    author_layers.main()

    # Step 4: Compose brief
    print(f"\n  Step 4: Composing unified brief...")
    from baselayer.agent_pipeline import compose_unified_brief, store_unified_brief
    brief = compose_unified_brief()
    if brief:
        store_unified_brief(None, brief)
        print(f"  Brief composed: {len(brief)} chars")
    else:
        print(f"  Composition failed.")
        sys.exit(1)

    # Update registry
    if source_dir:
        _update_manifest(subject_id, str(source_dir))

    # Update version + fact count in subjects table
    conn = _sql.connect(str(main_db))
    _subj_conn = _sql.connect(str(SUBJ_DB_FILE))
    fact_count = _subj_conn.execute("SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL").fetchone()[0]
    _subj_conn.close()

    new_version = f"V{(int(subject['version'].replace('V', '')) if subject['version'] else 1) + (1 if v2_mode else 0)}"
    conn.execute(
        "UPDATE subjects SET fact_count=?, version=?, status='complete', updated_at=datetime('now') WHERE id=?",
        (fact_count, new_version, subject_id)
    )
    conn.commit()
    conn.close()

    print(f"\n{'='*60}")
    print(f"  Pipeline complete — {name}")
    print(f"  Facts: {fact_count} | Version: {new_version}")
    print(f"{'='*60}\n")


def cmd_run(args):
    """One-command pipeline: import -> extract -> author -> compose + traceability (5 steps)."""
    from baselayer.config import DATABASE_FILE

    file_path = args.file
    if not Path(file_path).exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    _check_api_key()

    # Step 0: Init (if needed)
    if not DATABASE_FILE.exists():
        print(f"\n{'='*60}")
        print(f"  Initializing Base Layer")
        print(f"{'='*60}\n")
        cmd_init(args)
        if not DATABASE_FILE.exists():
            print("Initialization cancelled.")
            return
    else:
        print(f"\n  Database exists. Skipping init.")

    # Step 1: Import (skip if conversations already exist — prevents duplication on re-run)
    import sqlite3 as _sql
    _conn = _sql.connect(str(DATABASE_FILE))
    _existing = _conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
    _conn.close()
    if _existing > 0:
        print(f"\n  {_existing} conversations already imported. Skipping import.")
    else:
        print(f"\n{'='*60}")
        print(f"  Step 1/4: Importing data")
        print(f"{'='*60}\n")
        cmd_import(args)

    # Cost estimate + confirm
    print(f"\n{'='*60}")
    print(f"  Cost estimate")
    print(f"{'='*60}\n")
    cmd_estimate(args)

    if not args.yes:
        try:
            confirm = input("\n  Proceed with extraction? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            confirm = "n"
        if confirm == "n":
            print("  Cancelled. Your data is imported — run 'baselayer extract' when ready.")
            return

    # Step 2: Extract
    print(f"\n{'='*60}")
    print(f"  Step 2/4: Extracting facts")
    print(f"{'='*60}\n")
    if getattr(args, 'document_mode', False):
        import baselayer.extract_facts as extract_facts
        argv = ["extract_facts.py", "--document-mode"]
        if args.limit:
            argv.extend(["--limit", str(args.limit)])
        sys.argv = argv
        extract_facts.main()
    else:
        cmd_extract(args)

    # Step 3: Author (3 layers, no review)
    # Step 4: Compose (unified brief)
    print(f"\n{'='*60}")
    print(f"  Step 3-4/4: Authoring identity layers + composing brief")
    print(f"{'='*60}\n")
    args.layer = None
    args.no_citations = False
    args.compose = True
    cmd_author(args)

    # Step 5: Traceability (tier + embed + provenance + tensions)
    print(f"\n{'='*60}")
    print(f"  Step 5/5: Building traceability infrastructure")
    print(f"{'='*60}\n")
    _run_traceability()

    # Done — show result
    from baselayer.config import PROJECT_ROOT
    brief_path = PROJECT_ROOT / "data" / "identity_layers" / "brief_v5_clean.md"
    if brief_path.exists():
        brief_text = brief_path.read_text(encoding="utf-8")
        # Strip YAML header
        if brief_text.startswith("---"):
            end = brief_text.find("---", 3)
            if end > 0:
                brief_text = brief_text[end + 3:].strip()
        if brief_text.startswith("## Injectable Block"):
            brief_text = brief_text[len("## Injectable Block"):].strip()

        print(f"\n{'='*60}")
        print(f"  Done! Your identity brief is ready.")
        print(f"{'='*60}")
        print(f"\n  File: {brief_path}")
        print(f"  Length: {len(brief_text)} chars (~{len(brief_text) // 4} tokens)")
        print(f"\n  Preview (first 500 chars):")
        print(f"  {'-'*40}")
        for line in brief_text[:500].split("\n"):
            print(f"  {line}")
        print(f"  {'-'*40}")
        print(f"\n  Next steps:")
        print(f"    View full brief:  cat {brief_path}")
        print(f"    Add to Claude:    claude mcp add --transport stdio base-layer -- baselayer-mcp")
        print(f"    Interactive chat:  baselayer chat")
        print(f"    Review facts:     baselayer review")
    else:
        print(f"\n  Pipeline complete but no brief was generated.")
        print(f"  Run 'baselayer stats' to check your data.")


def _check_api_key():
    """Check that ANTHROPIC_API_KEY is set."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable not set.")
        print("Get your key at https://console.anthropic.com/")
        print("Then: export ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)


def _check_extraction_complete():
    """S98 gate: Block author/compose if extraction is incomplete.

    Compares extraction_log count against conversations that MEET the minimum
    message threshold — not all conversations. Short conversations (< MIN_MESSAGES)
    are intentionally skipped by extraction and shouldn't block the gate.
    """
    from baselayer.config import DATABASE_FILE, MIN_MESSAGES_FOR_EXTRACTION
    if not DATABASE_FILE.exists():
        return  # No DB yet — let downstream handle it

    import sqlite3
    conn = sqlite3.connect(str(DATABASE_FILE))
    try:
        # Only count conversations that meet extraction threshold
        extractable = conn.execute(
            "SELECT COUNT(*) FROM conversations WHERE message_count >= ?",
            (MIN_MESSAGES_FOR_EXTRACTION,)
        ).fetchone()[0]
        extracted = conn.execute("SELECT COUNT(*) FROM extraction_log").fetchone()[0]
        total_convs = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
    except Exception:
        conn.close()
        return  # Tables may not exist yet

    conn.close()

    if total_convs == 0:
        print("Error: No conversations imported. Run 'baselayer import' first.")
        sys.exit(1)

    if extractable > 0 and extracted < extractable:
        pct = (extracted / extractable * 100) if extractable > 0 else 0
        skipped = total_convs - extractable
        print(f"Error: Extraction incomplete — {extracted}/{extractable} extractable conversations ({pct:.0f}%).")
        if skipped > 0:
            print(f"  ({skipped} conversations below {MIN_MESSAGES_FOR_EXTRACTION}-message threshold, excluded)")
        print(f"Run 'baselayer extract' to finish extraction before authoring.")
        print(f"To force anyway (not recommended): set BASELAYER_SKIP_EXTRACTION_GATE=1")
        if not os.environ.get("BASELAYER_SKIP_EXTRACTION_GATE"):
            sys.exit(1)
        else:
            print(f"  WARNING: Proceeding despite incomplete extraction (gate overridden).")


def _check_fact_floor():
    """S98 Phase 3A: Block author/compose if fact quality is insufficient.

    Multi-dimensional check:
    - Identity-tier facts (behavioral + positional) >= 50
    - Distinct predicates >= 15
    - Source documents >= 5
    """
    from baselayer.config import DATABASE_FILE
    if not DATABASE_FILE.exists():
        return

    import sqlite3
    conn = sqlite3.connect(str(DATABASE_FILE))
    try:
        # Identity-tier behavioral + positional facts
        identity_facts = conn.execute("""
            SELECT COUNT(*) FROM memory_facts
            WHERE superseded_by IS NULL
              AND fact_type IN ('behavioral', 'positional')
              AND knowledge_tier = 'identity'
        """).fetchone()[0]

        # Distinct predicates
        distinct_preds = conn.execute("""
            SELECT COUNT(DISTINCT predicate) FROM memory_facts
            WHERE superseded_by IS NULL AND predicate IS NOT NULL
        """).fetchone()[0]

        # Source documents
        source_docs = conn.execute("""
            SELECT COUNT(DISTINCT source_conversation_id) FROM memory_facts
            WHERE superseded_by IS NULL
        """).fetchone()[0]
    except Exception:
        conn.close()
        return
    conn.close()

    failures = []
    if identity_facts < 50:
        failures.append(f"identity-tier facts: {identity_facts}/50")
    if distinct_preds < 15:
        failures.append(f"distinct predicates: {distinct_preds}/15")
    if source_docs < 5:
        failures.append(f"source documents: {source_docs}/5")

    if failures:
        print(f"Error: Fact quality below threshold — {', '.join(failures)}.")
        print(f"Extract more data or check extraction quality.")
        print(f"To force anyway: set BASELAYER_SKIP_FACT_FLOOR=1")
        if not os.environ.get("BASELAYER_SKIP_FACT_FLOOR"):
            sys.exit(1)
        else:
            print(f"  WARNING: Proceeding despite low fact quality (gate overridden).")


def _check_pipeline_lock():
    """S98 Phase 3A: Prevent concurrent pipeline runs (max 2).

    Uses a simple lock file with PID. Checks if PID is still alive.
    """
    from baselayer.config import PROJECT_ROOT
    lock_file = PROJECT_ROOT / "data" / ".pipeline.lock"
    lock_file.parent.mkdir(parents=True, exist_ok=True)

    current_pid = os.getpid()

    if lock_file.exists():
        try:
            content = lock_file.read_text().strip()
            pids = [int(p) for p in content.split("\n") if p.strip()]
            # Check which PIDs are still alive
            alive = []
            for pid in pids:
                try:
                    os.kill(pid, 0)  # Signal 0 = check if alive
                    alive.append(pid)
                except (OSError, ProcessLookupError):
                    pass  # Process dead

            if len(alive) >= 2:
                print(f"Error: {len(alive)} pipelines already running (max 2). PIDs: {alive}")
                print(f"Wait for one to finish or kill a process.")
                sys.exit(1)

            # Add our PID
            alive.append(current_pid)
            lock_file.write_text("\n".join(str(p) for p in alive))
        except (ValueError, IOError):
            # Corrupted lock file — overwrite
            lock_file.write_text(str(current_pid))
    else:
        lock_file.write_text(str(current_pid))

    # Register cleanup on exit
    import atexit
    def _cleanup_lock():
        try:
            if lock_file.exists():
                content = lock_file.read_text().strip()
                pids = [p for p in content.split("\n") if p.strip() and int(p) != current_pid]
                if pids:
                    lock_file.write_text("\n".join(pids))
                else:
                    lock_file.unlink(missing_ok=True)
        except Exception:
            pass
    atexit.register(_cleanup_lock)


def _snapshot_before_clear(memory_dir=None):
    """S98 Phase 3A: Snapshot current state before V2 clear.

    Copies memory.db + ChromaDB vectors to .snapshot/ directory.
    Returns snapshot path for potential restore.
    """
    from baselayer.config import DATABASE_FILE, VECTORS_DIR, PROJECT_ROOT
    import shutil
    from datetime import datetime

    base = Path(memory_dir) if memory_dir else PROJECT_ROOT
    db_path = base / "data" / "database" / "memory.db"
    vectors_path = base / "data" / "vectors"
    snapshot_dir = base / "data" / ".snapshot" / datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    if db_path.exists():
        shutil.copy2(str(db_path), str(snapshot_dir / "memory.db"))
        print(f"  Snapshot: database -> {snapshot_dir / 'memory.db'}")

    if vectors_path.exists():
        shutil.copytree(str(vectors_path), str(snapshot_dir / "vectors"))
        print(f"  Snapshot: vectors -> {snapshot_dir / 'vectors'}")

    print(f"  Snapshot saved: {snapshot_dir}")
    return snapshot_dir


def _check_manifest(subject_id, source_dir):
    """S98 Phase 3B: Block pipeline if source fingerprint unchanged since last run."""
    from baselayer.config import DATABASE_FILE, compute_source_fingerprint
    if not DATABASE_FILE.exists() or not source_dir:
        return

    import sqlite3
    fingerprint = compute_source_fingerprint(source_dir)
    if not fingerprint:
        return

    conn = sqlite3.connect(str(DATABASE_FILE))
    try:
        row = conn.execute(
            "SELECT source_fingerprint FROM subjects WHERE id = ?", (subject_id,)
        ).fetchone()
    except Exception:
        conn.close()
        return
    conn.close()

    if row and row[0] == fingerprint:
        print(f"Error: Source data unchanged since last pipeline run (fingerprint: {fingerprint[:12]}...).")
        print(f"Scrape new content before re-running, or set BASELAYER_SKIP_MANIFEST_GATE=1")
        if not os.environ.get("BASELAYER_SKIP_MANIFEST_GATE"):
            sys.exit(1)
        else:
            print(f"  WARNING: Proceeding despite unchanged source (gate overridden).")


def _update_manifest(subject_id, source_dir):
    """Store current source fingerprint in subjects table after successful run."""
    from baselayer.config import DATABASE_FILE, compute_source_fingerprint
    if not DATABASE_FILE.exists() or not source_dir:
        return

    import sqlite3
    fingerprint = compute_source_fingerprint(source_dir)
    if not fingerprint:
        return

    conn = sqlite3.connect(str(DATABASE_FILE))
    try:
        conn.execute(
            "UPDATE subjects SET source_fingerprint = ?, updated_at = datetime('now') WHERE id = ?",
            (fingerprint, subject_id)
        )
        conn.commit()
    except Exception:
        pass
    conn.close()


def cmd_subject(args):
    """S98 Phase 3B: Subject registry commands."""
    from baselayer.config import DATABASE_FILE
    import sqlite3

    if not DATABASE_FILE.exists():
        print("Error: No database. Run 'baselayer init' first.")
        sys.exit(1)

    conn = sqlite3.connect(str(DATABASE_FILE))
    conn.row_factory = sqlite3.Row

    if args.subject_action == "list":
        rows = conn.execute("""
            SELECT id, name, status, version, wave, tier, fact_count, sent
            FROM subjects ORDER BY wave, name
        """).fetchall()

        if not rows:
            print("No subjects in registry. Run migration script first.")
            conn.close()
            return

        print(f"\n{'ID':25s} {'Name':25s} {'Status':15s} {'Ver':4s} {'Wave':5s} {'Facts':>6s} {'Sent':>5s}")
        print("-" * 90)
        for r in rows:
            wave = str(r["wave"]) if r["wave"] else "-"
            sent = "Y" if r["sent"] else ""
            facts = str(r["fact_count"]) if r["fact_count"] else "-"
            print(f"{r['id']:25s} {r['name']:25s} {r['status']:15s} {r['version'] or 'V1':4s} {wave:5s} {facts:>6s} {sent:>5s}")
        print(f"\nTotal: {len(rows)} subjects")

    elif args.subject_action == "show":
        if not args.subject_id:
            print("Error: --id required for 'show'")
            sys.exit(1)
        row = conn.execute("SELECT * FROM subjects WHERE id = ?", (args.subject_id,)).fetchone()
        if not row:
            print(f"Subject '{args.subject_id}' not found")
            sys.exit(1)
        for key in row.keys():
            print(f"  {key:25s}: {row[key]}")

    conn.close()


def cmd_batch_extract(args):
    """Batch re-extraction via Anthropic Batch API."""
    _check_api_key()
    import baselayer.batch_extract as batch_extract

    if args.submit:
        batch_extract.run_submit()
    elif args.status:
        batch_extract.run_status()
    elif args.process:
        batch_extract.run_process()
    else:
        print("Specify --submit, --status, or --process")
        print("  --submit   Build prompts and submit batch")
        print("  --status   Check processing status")
        print("  --process  Process completed results")


def cmd_batch_classify(args):
    """Batch classification via Anthropic Batch API.

    NOTE: batch_classify.py is an archived script (pipeline simplification, S79).
    Classification is no longer part of the default 4-step pipeline.
    Script location: scripts/archive/dead_pipeline_steps/batch_classify.py
    """
    _check_api_key()
    import sys as _sys
    import os as _os
    _archive = _os.path.join(_os.path.dirname(__file__), "archive", "dead_pipeline_steps")
    _sys.path.insert(0, _archive)
    try:
        import batch_classify
        if args.submit:
            batch_classify.run_submit()
        elif args.status:
            batch_classify.run_status()
        elif args.process:
            batch_classify.run_process()
        else:
            print("Specify --submit, --status, or --process")
    finally:
        if _archive in _sys.path:
            _sys.path.remove(_archive)


def cmd_batch_tier(args):
    """Batch tier reclassification via Anthropic Batch API.

    NOTE: batch_tier.py is an archived script (pipeline simplification, S79).
    Tier reclassification is no longer part of the default 4-step pipeline.
    Script location: scripts/archive/dead_pipeline_steps/batch_tier.py
    """
    _check_api_key()
    import sys as _sys
    import os as _os
    _archive = _os.path.join(_os.path.dirname(__file__), "archive", "dead_pipeline_steps")
    _sys.path.insert(0, _archive)
    try:
        import batch_tier
        if args.submit:
            batch_tier.run_submit(source_tier=args.source_tier, subject=args.subject)
        elif args.status:
            batch_tier.run_status()
        elif args.process:
            batch_tier.run_process()
        else:
            print("Specify --submit, --status, or --process")
    finally:
        if _archive in _sys.path:
            _sys.path.remove(_archive)


def cmd_rebuild_fts(args):
    """Rebuild the FTS5 full-text search index from existing facts."""
    import sqlite3
    from baselayer.config import DATABASE_FILE, get_db

    if not DATABASE_FILE.exists():
        print("No database found. Run: baselayer init")
        sys.exit(1)

    with contextlib.closing(get_db()) as conn:
        # Check if FTS5 table exists
        fts_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_facts_fts'"
        ).fetchone()

        if not fts_exists:
            # Create FTS5 table and triggers
            print("  Creating FTS5 virtual table...")
            try:
                conn.executescript("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS memory_facts_fts USING fts5(
                        fact_text,
                        content='memory_facts',
                        content_rowid='rowid'
                    );

                    CREATE TRIGGER IF NOT EXISTS memory_facts_ai AFTER INSERT ON memory_facts BEGIN
                        INSERT INTO memory_facts_fts(rowid, fact_text) VALUES (new.rowid, new.fact_text);
                    END;

                    CREATE TRIGGER IF NOT EXISTS memory_facts_ad AFTER DELETE ON memory_facts BEGIN
                        INSERT INTO memory_facts_fts(memory_facts_fts, rowid, fact_text) VALUES('delete', old.rowid, old.fact_text);
                    END;

                    CREATE TRIGGER IF NOT EXISTS memory_facts_au AFTER UPDATE ON memory_facts BEGIN
                        INSERT INTO memory_facts_fts(memory_facts_fts, rowid, fact_text) VALUES('delete', old.rowid, old.fact_text);
                        INSERT INTO memory_facts_fts(rowid, fact_text) VALUES (new.rowid, new.fact_text);
                    END;
                """)
            except sqlite3.OperationalError as e:
                print(f"  Error: FTS5 not available in this SQLite build: {e}")
                print("  FTS5 is included in most SQLite distributions since 3.9.0.")
                sys.exit(1)

        # Rebuild the index from existing data
        print("  Rebuilding FTS5 index from existing facts...")
        conn.execute("INSERT INTO memory_facts_fts(memory_facts_fts) VALUES('rebuild')")
        conn.commit()

        # Verify
        fts_count = conn.execute("SELECT COUNT(*) FROM memory_facts_fts").fetchone()[0]
        fact_count = conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()[0]

        print(f"\n  FTS5 index rebuilt successfully.")
        print(f"  Indexed {fts_count} facts (total in DB: {fact_count})")
        print(f"  The search_facts MCP tool will now use FTS5 for faster lookups.")


def main():
    # Force UTF-8 stdout/stderr on Windows to prevent UnicodeEncodeError (cp1252)
    import sys as _sys
    if _sys.stdout.encoding and _sys.stdout.encoding.lower() != 'utf-8':
        import io
        _sys.stdout = io.TextIOWrapper(_sys.stdout.buffer, encoding='utf-8', errors='replace')
        _sys.stderr = io.TextIOWrapper(_sys.stderr.buffer, encoding='utf-8', errors='replace')

    parser = argparse.ArgumentParser(
        prog="baselayer",
        description="Base Layer - Personal AI Memory System",
        epilog="Learn more: https://github.com/baselayer-ai/baselayer",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s 0.1.0")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init
    p_init = subparsers.add_parser("init", help="Initialize a fresh database")
    p_init.add_argument("--force", action="store_true", help="Reinitialize (deletes data)")
    p_init.set_defaults(func=cmd_init)

    # import
    p_import = subparsers.add_parser("import", help="Import conversation history or text files")
    p_import.add_argument("file", help="Path to export file (.zip, .json) or text file/directory")
    p_import.add_argument("--source", choices=["chatgpt", "claude_web", "claude_code", "journal", "text"],
                          help="Source type (auto-detected if omitted)")
    p_import.set_defaults(func=cmd_import)

    # estimate
    p_estimate = subparsers.add_parser("estimate", help="Estimate API cost for extraction")
    p_estimate.set_defaults(func=cmd_estimate)

    # extract
    p_extract = subparsers.add_parser("extract", help="Extract facts from conversations")
    p_extract.add_argument("--limit", type=int, help="Max conversations to process")
    p_extract.add_argument("--backend", choices=["ollama", "anthropic"],
                           help="LLM backend (default: anthropic)")
    p_extract.add_argument("--identity-only", action="store_true",
                           help="Extract only identity-relevant facts from project conversations (D-048)")
    p_extract.add_argument("--source", choices=["chatgpt", "claude_code", "claude_web", "journal", "text_file"],
                           help="Filter to a specific conversation source")
    p_extract.add_argument("--document-mode", action="store_true",
                           help="Document extraction mode (papers, books, patents)")
    p_extract.set_defaults(func=cmd_extract)

    # embed
    p_embed = subparsers.add_parser("embed", help="Generate vector embeddings")
    p_embed.set_defaults(func=cmd_embed)

    # author
    p_author = subparsers.add_parser("author", help="Generate identity layers (Sonnet API)")
    p_author.add_argument("--layer", choices=["anchors", "core", "predictions", "all"],
                          help="Which layer to generate (default: all)")
    p_author.add_argument("--no-citations", action="store_true",
                          help="Disable Citations API (use self-citation fallback)")
    p_author.add_argument("--compose", action="store_true",
                          help="Chain unified brief composition after layer generation")
    p_author.set_defaults(func=cmd_author)

    # compose (S62 — unified brief from deployed layers)
    p_compose = subparsers.add_parser("compose",
        help="Compose unified narrative brief from deployed identity layers (Opus API)")
    p_compose.set_defaults(func=cmd_compose)

    # brief
    p_brief = subparsers.add_parser("brief",
        help="[ARCHIVED] Assemble a context-retrieval brief via assemble_brief.py — "
             "use 'compose' for the current V4 unified brief")
    p_brief.add_argument("message", help="The message to build the brief for")
    p_brief.set_defaults(func=cmd_brief)

    # chat
    p_chat = subparsers.add_parser("chat",
        help="[ARCHIVED] Interactive memory-augmented chat via assemble_brief.py — "
             "kept for compatibility, not part of the 4-step pipeline")
    p_chat.set_defaults(func=cmd_chat)

    # subject (S98 Phase 3B)
    p_subject = subparsers.add_parser("subject", help="Subject registry (list/show)")
    p_subject.add_argument("subject_action", choices=["list", "show"], help="Action")
    p_subject.add_argument("--id", dest="subject_id", help="Subject ID (for show)")
    p_subject.set_defaults(func=cmd_subject)

    # stats
    p_stats = subparsers.add_parser("stats", help="Show database statistics")
    p_stats.set_defaults(func=cmd_stats)

    # search
    p_search = subparsers.add_parser("search", help="Search facts")
    p_search.add_argument("query", help="Search query")
    p_search.set_defaults(func=cmd_search)

    # forget
    p_forget = subparsers.add_parser("forget", help="Soft-delete facts (by ID, conversation, or all)")
    p_forget.add_argument("--fact", type=str, metavar="ID",
                          help="Delete a specific fact by its ID")
    p_forget.add_argument("--conversation", type=str, metavar="ID",
                          help="Delete all facts from a conversation ID")
    p_forget.add_argument("--all", action="store_true",
                          help="Delete ALL active facts (requires confirmation)")
    p_forget.set_defaults(func=cmd_forget)

    # provenance (S56 — trace layer claims to source facts)
    p_prov = subparsers.add_parser("provenance", help="Trace identity layer claims to supporting facts")
    p_prov.add_argument("--claim", type=str, metavar="ID",
                         help="Trace a specific claim by lexicon ID (e.g. A1, P3, C2)")
    p_prov.set_defaults(func=cmd_provenance)

    # verify (S57 — vector + claim verification)
    p_verify = subparsers.add_parser("verify",
        help="Verify identity layer provenance (vector similarity + claim checks)")
    p_verify.add_argument("--layer", choices=["anchors", "core", "predictions", "all"],
                           default="all", help="Which layer to verify (default: all)")
    verify_mode = p_verify.add_mutually_exclusive_group()
    verify_mode.add_argument("--vector", action="store_true",
                              help="Run vector verification only (skip claim checks)")
    verify_mode.add_argument("--claims", action="store_true",
                              help="Run claim verification only (skip vector audit)")
    verify_mode.add_argument("--nli", action="store_true",
                              help="Run NLI entailment verification (DeBERTa, local, ~400ms/pair)")
    verify_mode.add_argument("--generate", action="store_true",
                              help="Generate vector provenance from scratch (for layers missing citation provenance)")
    p_verify.add_argument("--claim", type=str, metavar="ID",
                           help="Verify a specific claim (e.g. A1, P3, C2)")
    p_verify.set_defaults(func=cmd_verify)

    # review
    p_review = subparsers.add_parser("review", help="Review and correct facts interactively")
    p_review.add_argument("--tier", choices=["identity", "situational", "context"],
                          help="Filter by knowledge tier")
    p_review.add_argument("--limit", type=int, default=50,
                          help="Max facts to review (default: 50)")
    p_review.set_defaults(func=cmd_review)

    # journal
    p_journal = subparsers.add_parser("journal", help="Guided journal prompts for identity building")
    p_journal.set_defaults(func=cmd_journal)

    # checkpoint (Session 49 -- quality gates; scoring/classification stages archived in S79)
    p_checkpoint = subparsers.add_parser("checkpoint",
        help="Pipeline quality checkpoints (extraction/all)")
    p_checkpoint.add_argument("stage", choices=["extraction", "scoring", "classification", "all"],
                              help="Which checkpoint to run (scoring/classification are legacy stages from pre-S79 pipeline)")
    p_checkpoint.set_defaults(func=cmd_checkpoint)

    # batch-extract (Session 50 -- Anthropic Batch API re-extraction)
    p_batch = subparsers.add_parser("batch-extract",
        help="Batch re-extraction via Anthropic Batch API (50%% cost)")
    p_batch.add_argument("--submit", action="store_true",
                         help="Build prompts and submit batch to Anthropic API")
    p_batch.add_argument("--status", action="store_true",
                         help="Check batch processing status")
    p_batch.add_argument("--process", action="store_true",
                         help="Process completed batch results into database")
    p_batch.set_defaults(func=cmd_batch_extract)

    # batch-classify (Session 73 — Batch API classification, 50% cost)
    p_bclass = subparsers.add_parser("batch-classify",
        help="[ARCHIVED] Batch classification via Anthropic Batch API (removed in S79 simplification)")
    p_bclass.add_argument("--submit", action="store_true",
                          help="Build prompts and submit batch")
    p_bclass.add_argument("--status", action="store_true",
                          help="Check batch processing status")
    p_bclass.add_argument("--process", action="store_true",
                          help="Process completed batch results")
    p_bclass.set_defaults(func=cmd_batch_classify)

    # batch-tier (Session 73 — Batch API tier reclassification, 50% cost)
    p_btier = subparsers.add_parser("batch-tier",
        help="[ARCHIVED] Batch tier reclassification via Anthropic Batch API (removed in S79 simplification)")
    p_btier.add_argument("--submit", action="store_true",
                         help="Build prompts and submit batch")
    p_btier.add_argument("--status", action="store_true",
                         help="Check batch processing status")
    p_btier.add_argument("--process", action="store_true",
                         help="Process completed batch results")
    p_btier.add_argument("--source-tier", choices=["context", "situational"],
                         default="context", help="Tier to promote from (default: context)")
    p_btier.add_argument("--subject", type=str, default=None,
                         help="Primary subject name for document corpora")
    p_btier.set_defaults(func=cmd_batch_tier)

    # rebuild-fts (Session 57 — C11: FTS5 full-text search index)
    p_fts = subparsers.add_parser("rebuild-fts",
        help="Rebuild FTS5 full-text search index from existing facts")
    p_fts.set_defaults(func=cmd_rebuild_fts)

    # ui (Session 72 — local drag-and-drop web UI)
    p_ui = subparsers.add_parser("ui",
        help="Launch local web UI for drag-and-drop pipeline")
    p_ui.add_argument("--port", type=int, default=3141, help="Port (default: 3141)")
    p_ui.add_argument("--no-browser", action="store_true", help="Don't auto-open browser")
    p_ui.set_defaults(func=lambda args: __import__('ui').main())

    # pipeline (S98 Phase 4 — unified command with gates)
    p_pipeline = subparsers.add_parser("pipeline",
        help="Unified pipeline: import > extract > author > compose (with all gates)")
    p_pipeline.add_argument("subject_id", help="Subject ID from registry (e.g., kevin_kelly)")
    p_pipeline.add_argument("--v2", action="store_true",
        help="V2 mode: snapshot, clear, re-extract with expanded corpus")
    p_pipeline.add_argument("--yes", "-y", action="store_true",
        help="Skip confirmation prompts")
    p_pipeline.set_defaults(func=cmd_pipeline)

    # run (legacy — kept for backward compat, use 'pipeline' for new work)
    p_run = subparsers.add_parser("run",
        help="One-command pipeline: import > extract > author > compose")
    p_run.add_argument("file", help="Path to export file (.zip, .json) or text file/directory")
    p_run.add_argument("--source", choices=["chatgpt", "claude_web", "claude_code", "journal", "text"],
                        help="Source type (auto-detected if omitted)")
    p_run.add_argument("--yes", "-y", action="store_true",
                        help="Skip confirmation prompts")
    p_run.add_argument("--document-mode", action="store_true",
                        help="Use document extraction mode (for papers, books, patents)")
    p_run.add_argument("--subject", type=str,
                        help="Subject name for document mode tiering")
    # Needed by sub-commands but not directly used
    p_run.add_argument("--force", action="store_true", help=argparse.SUPPRESS)
    p_run.add_argument("--limit", type=int, default=None, help=argparse.SUPPRESS)
    p_run.add_argument("--backend", default=None, help=argparse.SUPPRESS)
    p_run.add_argument("--identity-only", action="store_true", help=argparse.SUPPRESS)
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
