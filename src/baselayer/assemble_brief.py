"""
Phase 5: Context Projection + Brief Assembly (D-025: The Ghost Layer)

The product. Everything built in Phases 1-4 feeds into this one thing: a ~1,500
token brief injected into Claude's system prompt so the AI feels like it *knows* you.

Three blocks:
  1. Identity (~500 tokens, always-on) — who you are, always present
  2. Themes (~500 tokens, retrieved) — what matters right now, based on message
  3. Episodes (~500 tokens, retrieved) — "I remember when you said..." moments

The Ghost Layer (D-025):
  Woven through the system as constants, weights, and structure decisions is an
  invisible set of priors about what matters to humans. Family carries inherent
  weight. Motivations are core identity. Loss shapes a person. The code looks like
  well-designed weights. The philosophy behind them is documented in
  DESIGN_PRINCIPLES.md but invisible in the code.

Run:
  python assemble_brief.py --generate-identity       # Retrieve cluster facts for authoring
  python assemble_brief.py --store-identity "text"   # Store a pre-written identity block
  python assemble_brief.py --store-identity @file    # Store from file (relative to data/)
  python assemble_brief.py --assemble "message"      # Full brief for a message
  python assemble_brief.py --interactive              # Chat with Claude using the brief
  python assemble_brief.py --test                     # Run 20-case evaluation harness
  python assemble_brief.py --show-identity            # Show current identity block
  python assemble_brief.py --show-brief "message"     # Show brief without sending to Claude
"""

import contextlib
import sys
import io
import sqlite3
import json
import time
import math
import argparse
import os
import requests
from pathlib import Path
from datetime import datetime

# NOTE: sys.stdout/stderr wrappers moved to if __name__ == "__main__" block
# to avoid corrupting pytest's capture mechanism on import.

# ---------------------------------------------------------------------------
# Shared config — single source of truth (config.py)
# ---------------------------------------------------------------------------
from baselayer.config import (
    PROJECT_ROOT, DATABASE_FILE, VECTORS_DIR,
    EMBEDDING_MODEL, OLLAMA_URL, LLM_MODEL,
    CHARS_PER_TOKEN, IDENTITY_TOKEN_BUDGET, THEME_TOKEN_BUDGET,
    EPISODE_TOKEN_BUDGET, TOTAL_TOKEN_BUDGET,
    THEME_FACTS_TO_RETRIEVE, THEME_SUMMARIES_TO_RETRIEVE,
    THEME_TURN_PAIRS_TO_RETRIEVE, THEME_FACTS_TO_KEEP,
    EPISODE_COUNT, ASSOCIATIVE_BOOST,
    ANCHORS_LAYER_FILE, CORE_LAYER_FILE, PREDICTIONS_LAYER_FILE,
    TEMPORAL_QUALIFIER_THRESHOLD_DAYS, RECENCY_DECAY_WINDOW_DAYS,
    get_db,
)

# ===========================================================================
# IDENTITY CLUSTER FRAMEWORK (D-026)
# ===========================================================================
# The Ghost Layer lives here — not as per-fact weights, but as the schema
# itself. The fact that "what you've lost" is a cluster at all is a prior
# about human identity. The data fills the clusters; the clusters define
# what questions to ask about a person.
#
# Each cluster has:
#   - keywords: terms to match in fact text (primary retrieval)
#   - categories: which fact categories typically belong here
#   - temporal_bias: which time horizons to prefer
#   - volatility: how fast this dimension changes (affects trust in old data)
#   - token_budget: how many tokens this cluster gets in the identity block
#   - max_facts: how many representative facts to send to Qwen for this cluster
# ===========================================================================

IDENTITY_CLUSTERS = {
    "who_you_are": {
        "label": "Who you are",
        "description": "Age, personal background, where they live, education, core biographical facts",
        "categories": ["biography"],
        "temporal_bias": ["foundational", "active"],
        "volatility": "low",
        "token_budget": 80,
        "max_facts": 4,
    },
    "who_you_love": {
        "label": "Who you love",
        "description": "Spouse, partner, family members, pets, close relationships and how they feel about these people",
        "categories": ["relationship"],
        "temporal_bias": ["foundational", "formative", "active"],
        "volatility": "low",
        "token_budget": 100,
        "max_facts": 4,
    },
    "what_youve_built": {
        "label": "What you've built",
        "description": "Companies, products, projects, teams led, creative works, professional achievements, systems developed through experience",
        "categories": ["project", "skill", "biography"],
        "temporal_bias": ["formative", "active"],
        "volatility": "low-medium",
        "token_budget": 100,
        "max_facts": 4,
    },
    "what_youve_lost": {
        "label": "What you've lost",
        "description": "Failed ventures, departed roles, ended relationships, disillusionment, significant losses that taught lessons",
        "categories": ["project", "biography", "negative_trait"],
        "temporal_bias": ["foundational", "formative", "active"],
        "volatility": "low",
        "token_budget": 80,
        "max_facts": 3,
    },
    "what_drives_you": {
        "label": "What drives you",
        "description": "Deep personal values, inner motivation, what they care most about in life and work",
        "categories": ["value", "goal"],
        "temporal_bias": ["formative", "foundational"],
        "volatility": "medium",
        "token_budget": 90,
        "max_facts": 4,
    },
    "what_you_believe": {
        "label": "What you believe",
        "description": "Worldview, convictions, beliefs about how the world works, philosophy of knowledge",
        "categories": ["opinion", "value"],
        "temporal_bias": ["formative", "active"],
        "volatility": "medium",
        "token_budget": 80,
        "max_facts": 3,
    },
    "what_you_struggle_with": {
        "label": "What you struggle with",
        "description": "Personal weaknesses, recurring failure modes, self-doubt, negative personality traits",
        "categories": ["negative_trait"],
        "temporal_bias": ["active", "formative"],
        "volatility": "medium-high",
        "token_budget": 80,
        "max_facts": 4,
    },
    "how_you_operate": {
        "label": "How you operate",
        "description": "Communication style, decision-making approach, habits, routines, how they interact with others",
        "categories": ["habit", "preference"],
        "temporal_bias": ["formative", "active"],
        "volatility": "medium",
        "token_budget": 80,
        "max_facts": 3,
    },
    "where_youre_headed": {
        "label": "Where you're headed",
        "description": "Future goals, what they are actively building or working toward, current projects and aspirations",
        "categories": ["goal", "project"],
        "temporal_bias": ["active"],
        "volatility": "high",
        "token_budget": 60,
        "max_facts": 3,
    },
    "whats_unresolved": {
        "label": "What's unresolved",
        "description": "Open questions, active contradictions, things the system doesn't know",
        "categories": [],
        "temporal_bias": ["active"],
        "volatility": "high",
        "token_budget": 30,
        "max_facts": 2,
    },
}

# Total token budget across all clusters: ~780 tokens
# (80+100+100+80+90+80+80+80+60+30 = 780)
# With Qwen's prose compression this typically fits within 800 token identity budget


# ===========================================================================
# CLUSTER-BASED RETRIEVAL (D-026)
# ===========================================================================
# Each cluster retrieves its own facts independently. No composite formula.
# Facts are matched by keyword + category, then ranked by recurrence
# (the one data signal that actually varies across facts).
# ===========================================================================

def get_chroma_client():
    """Get ChromaDB client (cached)."""
    if not hasattr(get_chroma_client, "_client"):
        import chromadb
        get_chroma_client._client = chromadb.PersistentClient(path=str(VECTORS_DIR))
    return get_chroma_client._client


def retrieve_cluster_facts(conn, cluster_key, cluster_config):
    """
    Retrieve candidate facts for a single identity cluster.

    Strategy: semantic search using the cluster description as the query.
    ChromaDB finds facts whose meaning matches the cluster intent, regardless
    of specific keywords. Then we look up full fact data from SQLite.
    """
    max_facts = cluster_config["max_facts"]
    label = cluster_config["label"]
    description = cluster_config["description"]

    if not description:
        return []

    # Semantic search: query ChromaDB with the cluster description
    try:
        client = get_chroma_client()
        coll = client.get_collection("memory_facts")

        # Search for facts semantically similar to the cluster description
        query_text = f"{label}: {description}"
        results = coll.query(
            query_texts=[query_text],
            n_results=max_facts * 15,  # Get plenty of candidates
        )

        if not results["ids"][0]:
            return []

        # Get SQLite fact IDs from ChromaDB metadata
        chroma_fact_ids = []
        for meta in results["metadatas"][0]:
            if "fact_id" in meta:
                chroma_fact_ids.append(meta["fact_id"])

        if not chroma_fact_ids:
            return []

        # Look up full fact data from SQLite (only active facts)
        placeholders = ",".join("?" * len(chroma_fact_ids))
        rows = conn.execute(
            "SELECT id, fact_text, category, confidence, significance_score,"
            "       recurrence_count, depth_score, significance_type,"
            "       subject, intent, temporal_state, sentiment"
            " FROM memory_facts"
            " WHERE id IN (" + placeholders + ")"
            " AND superseded_by IS NULL"
            " ORDER BY significance_score DESC, recurrence_count DESC",
            chroma_fact_ids
        ).fetchall()

        # Filter out job-application/aspirational facts that Qwen confuses
        # with biographical facts (e.g., "personalizing resume for CEO role
        # at Morio" gets hallucinated as "founded Morio")
        _JOB_APP_SIGNALS = [
            "resume", "cover letter", "job application", "applying to",
            "applying for", "personalizing", "job posting", "interview prep",
            "linkedin profile", "job search", "role at", "looking for a",
            "looking for job", "job opportunities", "full-time",
            "looking for roles", "looking to transition", "transition into",
            "interested in roles", "account manager", "solutions consultant",
            "customer success", "product operations", "business operations",
            "strategy & operations", "technical account",
            # D-027 additions: aspirational/mission-statement leaks
            "vast's vision", "vast's mission", "billions of people",
            "drawn to", "contributing to a future",
        ]
        filtered = []
        for row in rows:
            text_lower = row["fact_text"].lower()
            is_job_app = any(signal in text_lower for signal in _JOB_APP_SIGNALS)
            if is_job_app:
                continue  # Skip all job-search/application facts from identity
            filtered.append(row)

        return filtered

    except Exception as e:
        print(f"    ChromaDB search failed for {cluster_key}: {e}")
        return []


def pick_best_representatives(conn, cluster_key, cluster_config, candidate_facts):
    """
    Have Qwen pick the best representative facts for a cluster.

    Simple prompt: "Which of these facts best captures [cluster description]?"
    Falls back to top-by-recurrence if Qwen is unavailable.
    """
    max_facts = cluster_config["max_facts"]
    label = cluster_config["label"]
    description = cluster_config["description"]

    if not candidate_facts:
        return []

    # If we have fewer candidates than needed, just return them all
    if len(candidate_facts) <= max_facts:
        return candidate_facts

    # Try Qwen for smart selection
    facts_text = "\n".join(
        f"{i+1}. [{r['category']}] {r['fact_text']}"
        for i, r in enumerate(candidate_facts[:30])  # Cap at 30 for prompt size
    )

    prompt = f"""From these facts about a person, pick the {max_facts} that BEST capture: "{label} — {description}"

Rules:
- Pick facts that are specific and concrete (names, numbers, real details)
- Avoid duplicates — if two facts say the same thing, pick the better-written one
- Prefer facts that tell a story over facts that state an attribute
- Return ONLY the numbers, comma-separated. Example: 3, 7, 12

FACTS:
{facts_text}

Best {max_facts} (numbers only):"""

    try:
        payload = {
            "model": LLM_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 50},
        }
        response = requests.post(OLLAMA_URL, json=payload, timeout=60)
        response.raise_for_status()
        answer = response.json().get("response", "").strip()

        # Parse numbers from response
        import re
        numbers = [int(n) for n in re.findall(r'\d+', answer)]
        selected = []
        for n in numbers:
            if 1 <= n <= len(candidate_facts) and len(selected) < max_facts:
                selected.append(candidate_facts[n - 1])

        if selected:
            return selected
    except Exception as e:
        print(f"    Qwen selection failed for {cluster_key}: {e}, falling back to recurrence")

    # Fallback: top by recurrence (skip near-duplicates by checking text similarity)
    selected = []
    selected_texts = []
    for row in candidate_facts:
        if len(selected) >= max_facts:
            break
        # Simple dedup: skip if >60% word overlap with already-selected fact
        words = set(row["fact_text"].lower().split())
        is_dup = False
        for prev_text in selected_texts:
            prev_words = set(prev_text.lower().split())
            if len(words & prev_words) / max(len(words | prev_words), 1) > 0.6:
                is_dup = True
                break
        if not is_dup:
            selected.append(row)
            selected_texts.append(row["fact_text"])

    return selected


def build_unresolved_cluster(conn, all_cluster_facts):
    """
    Build the 'what's unresolved' cluster from tensions and gaps.

    Looks for: contradictions between self-view and behavior,
    clusters with very few facts (knowledge gaps), and
    facts with mixed sentiment (unresolved feelings).
    """
    unresolved = []

    # Find facts with mixed sentiment — unresolved feelings
    rows = conn.execute("""
        SELECT id, fact_text, category, confidence, significance_score,
               recurrence_count, depth_score, significance_type,
               subject, intent, temporal_state, sentiment
        FROM memory_facts
        WHERE superseded_by IS NULL AND sentiment = 'mixed'
        ORDER BY recurrence_count DESC
        LIMIT 5
    """).fetchall()
    unresolved.extend(rows[:2])

    return unresolved


def retrieve_all_clusters(conn):
    """
    Retrieve and select representative facts for all identity clusters.

    Returns dict: {cluster_key: [selected_fact_rows]}
    """
    print("\n=== Retrieving Identity Clusters ===\n")

    all_cluster_facts = {}

    for cluster_key, config in IDENTITY_CLUSTERS.items():
        if cluster_key == "whats_unresolved":
            continue  # Handled separately

        candidates = retrieve_cluster_facts(conn, cluster_key, config)
        print(f"  {config['label']:25s} — {len(candidates):3d} candidates found")

        if candidates:
            selected = pick_best_representatives(conn, cluster_key, config, candidates)
            all_cluster_facts[cluster_key] = selected
            for fact in selected:
                print(f"    -> {fact['fact_text'][:90]}")
        else:
            all_cluster_facts[cluster_key] = []
            print(f"    -> (empty — knowledge gap)")

    # Build unresolved cluster from tensions
    unresolved = build_unresolved_cluster(conn, all_cluster_facts)
    all_cluster_facts["whats_unresolved"] = unresolved
    if unresolved:
        print(f"  {'Whats unresolved':25s} — {len(unresolved)} tensions found")
        for fact in unresolved:
            print(f"    -> {fact['fact_text'][:90]}")
    else:
        print(f"  {'Whats unresolved':25s} — (no tensions detected)")

    return all_cluster_facts


# ===========================================================================
# DATABASE HELPERS
# ===========================================================================

def get_db_connection():
    """Get a database connection with row factory.
    Delegates to config.get_db() — single source of truth for connection setup.
    """
    return get_db()


def create_tables(conn):
    """Create tables for identity blocks and brief assembly logs."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS identity_blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            block_text TEXT NOT NULL,
            token_count INTEGER,
            fact_ids TEXT,
            created_at REAL,
            approved INTEGER DEFAULT 0,
            notes TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS brief_assembly_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_message TEXT,
            identity_tokens INTEGER,
            theme_tokens INTEGER,
            episode_tokens INTEGER,
            total_tokens INTEGER,
            facts_used INTEGER,
            episodes_used INTEGER,
            assembly_time_ms REAL,
            created_at REAL
        )
    """)
    conn.commit()


# ===========================================================================
# BLOCK 1: IDENTITY GENERATION
# ===========================================================================

def generate_identity_block(conn):
    """
    Retrieve and display cluster facts for identity block authoring (D-026 + D-030).

    This function does NOT generate narrative text. It retrieves structured facts
    from each identity cluster and displays them so they can be used by a human
    or Claude Code session to write the identity block. The written block is then
    stored via --store-identity.

    Steps:
      1. Retrieve candidate facts for each identity cluster (ChromaDB + SQLite)
      2. Display them grouped by cluster with recurrence/significance metadata
      3. Show recent user corrections for context
    """
    print("\n=== Identity Block Fact Retrieval (D-026 Clusters) ===\n")

    # Step 1: Retrieve candidate facts for each cluster
    cluster_facts = retrieve_all_clusters(conn)

    # Count total facts
    total_facts = sum(len(facts) for facts in cluster_facts.values())
    non_empty = sum(1 for facts in cluster_facts.values() if facts)
    print(f"\n  Total: {total_facts} candidate facts across {non_empty}/{len(IDENTITY_CLUSTERS)} clusters")

    if total_facts == 0:
        print("  ERROR: No facts found for any cluster. Run extract_facts.py first.")
        return None

    # Step 2: Display ALL cluster facts with metadata
    print("\n" + "=" * 70)
    print("CLUSTER FACTS FOR IDENTITY BLOCK AUTHORING")
    print("=" * 70)

    all_fact_ids = []

    for cluster_key, config in IDENTITY_CLUSTERS.items():
        facts = cluster_facts.get(cluster_key, [])
        if not facts:
            continue

        label = config["label"]
        print(f"\n### {label}")
        for r in facts:
            rec = r["recurrence_count"] or 0
            sig = r["significance_score"] or 0
            print(f"  - {r['fact_text']} [recurrence: {rec}, significance: {sig:.1f}]")
            all_fact_ids.append(r["id"])

    # Step 3: Show recent corrections
    try:
        corrections = conn.execute("""
            SELECT correction_type, original_fact_text, corrected_fact_text, notes
            FROM user_corrections
            ORDER BY created_at DESC
            LIMIT 15
        """).fetchall()
        if corrections:
            print(f"\n### Recent Corrections")
            for c in corrections:
                if c["correction_type"] == "DELETE":
                    print(f"  - WRONG: \"{c['original_fact_text'][:80]}\" — {c['notes'] or 'deleted'}")
                elif c["correction_type"] == "REPLACE":
                    print(f"  - CORRECTED: \"{c['corrected_fact_text'][:80]}\"")
    except Exception:
        pass

    print(f"\n{'=' * 70}")
    print(f"Use these facts to write the identity block in a Claude Code session,")
    print(f"then store it with: python assemble_brief.py --store-identity \"<text>\"")
    print(f"Or store from file: python assemble_brief.py --store-identity-file path/to/block.txt")
    print(f"{'=' * 70}\n")

    return all_fact_ids


def store_identity_block(conn, identity_text, notes=""):
    """
    Validate and store a pre-written identity block.

    Runs the rejection gate (voice, filter, entities, filler) but stores
    the block regardless — gate failures are logged as warnings for review.
    """
    import re as _re

    print("\n=== Storing Identity Block ===\n")

    if not identity_text or len(identity_text.strip()) < 50:
        print("  ERROR: Identity text is too short (< 50 chars).")
        return None

    identity_text = identity_text.strip()

    # ---------------------------------------------------------------
    # REJECTION GATE: 5-check scorecard (voice, filter, entities, filler, sourcing)
    # ---------------------------------------------------------------
    def _run_rejection_gate(text):
        """Run 5-check scorecard on identity block. Returns (pass, failures)."""
        failures = []

        # Check 1: Voice compliance — should be 2nd person ("you"), not 3rd ("he/his/him")
        sentences = _re.split(r'[.!?]\s+', text)
        third_person_count = 0
        second_person_count = 0
        for s in sentences:
            words = s.lower().split()
            if any(w in words for w in ["he", "his", "him", "he's", "he'd"]):
                third_person_count += 1
            if any(w in words for w in ["you", "your", "you're", "you've", "you'd"]):
                second_person_count += 1
        if third_person_count > second_person_count:
            failures.append(f"VOICE: {third_person_count} third-person vs {second_person_count} second-person sentences")

        # Check 2: Job-app/aspirational filter on output text
        _OUTPUT_FILTER = [
            "vast's vision", "vast's mission", "billions of people",
            "drawn to missions", "contributing to a future",
            "leadership opportunities", "long-term growth and leadership",
        ]
        text_lower = text.lower()
        for signal in _OUTPUT_FILTER:
            if signal in text_lower:
                failures.append(f"FILTER: '{signal}' leaked into identity block")

        # Check 3: Motivational filler detection
        _FILLER_PHRASES = [
            "warts and all", "what makes him real", "what makes you real",
            "that's what makes", "real and relatable", "complex and multifaceted",
            "at the end of the day", "it's all about the journey",
            "incredible drive", "blend of sharp intellect",
        ]
        for phrase in _FILLER_PHRASES:
            if phrase in text_lower:
                failures.append(f"FILLER: '{phrase}'")

        return len(failures) == 0, failures

    gate_pass, gate_failures = _run_rejection_gate(identity_text)

    if not gate_pass:
        print(f"  REJECTION GATE: {len(gate_failures)} issue(s) detected:")
        for f in gate_failures:
            print(f"    - {f}")
        print(f"  Storing with warnings for review.")
    else:
        print(f"  Rejection gate: PASSED")

    # Estimate token count
    token_count = len(identity_text) // CHARS_PER_TOKEN

    # Build notes with gate status
    gate_status = "PASSED" if gate_pass else f"FAILED ({len(gate_failures)} issues)"
    full_notes = f"Claude Code session authored. Gate: {gate_status}"
    if notes:
        full_notes += f" | {notes}"
    if not gate_pass:
        full_notes += " | " + " | ".join(gate_failures)

    # Store in database
    conn.execute("""
        INSERT INTO identity_blocks (block_text, token_count, fact_ids, created_at, notes)
        VALUES (?, ?, ?, ?, ?)
    """, (
        identity_text,
        token_count,
        "[]",
        time.time(),
        full_notes,
    ))
    conn.commit()

    block_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    print(f"\n  Identity block #{block_id} stored ({token_count} tokens, {len(identity_text)} chars)")
    print(f"  Gate: {gate_status}")
    print(f"\n--- IDENTITY BLOCK ---")
    print(identity_text)
    print(f"--- END ---\n")

    return block_id


def _read_injectable_block(file_path):
    """Read the injectable block from a layer markdown file."""
    if not file_path.exists():
        return None
    content = file_path.read_text(encoding="utf-8")
    marker = "## Injectable Block"
    idx = content.find(marker)
    if idx >= 0:
        return content[idx + len(marker):].strip()
    sep_idx = content.find("\n---\n")
    if sep_idx >= 0:
        return content[sep_idx + 5:].strip()
    return content.strip()


def get_three_layer_identity():
    """
    Read the three-layer identity from layer files (D-043).

    Returns assembled identity text with XML sub-blocks, or None if no layers exist.
    """
    anchors = _read_injectable_block(ANCHORS_LAYER_FILE)
    core = _read_injectable_block(CORE_LAYER_FILE)
    predictions = _read_injectable_block(PREDICTIONS_LAYER_FILE)

    if not any([anchors, core, predictions]):
        return None

    parts = []
    if anchors:
        parts.append("<epistemic_anchors>")
        parts.append(anchors)
        parts.append("</epistemic_anchors>")
        parts.append("")
    if core:
        parts.append("<individual_overview>")
        parts.append(core)
        parts.append("</individual_overview>")
        parts.append("")
    if predictions:
        parts.append("<behavioral_predictions>")
        parts.append(predictions)
        parts.append("</behavioral_predictions>")

    return "\n".join(parts)


def get_current_identity(conn):
    """
    Get the current identity block.

    Priority:
      0. Unified brief file (S62 — compressed narrative, proven +0.40 vs layers)
      1. Three-layer files (D-043) — if any layer file exists, use them
      2. Legacy: most recently approved identity_blocks row
      3. Legacy: latest unapproved identity_blocks row
    """
    usage_preamble = (
        "IMPORTANT: This brief contains ALL-CAPS pattern names as internal labels. NEVER "
        "quote, reference, or name them in your responses. Do not say 'your [PATTERN] axiom' or "
        "'the [PATTERN-NAME] pattern.' Instead, demonstrate understanding through your behavior: "
        "how you frame questions, what you push back on, what you anticipate. "
        "Match response length to question complexity — default shorter."
    )

    # Try unified brief first (S62: compression > structured layers)
    from baselayer.config import UNIFIED_BRIEF_FILE
    if UNIFIED_BRIEF_FILE.exists():
        block = _read_injectable_block(UNIFIED_BRIEF_FILE)
        if block:
            return f"{usage_preamble}\n\n{block}"

    # Try three-layer format
    three_layer = get_three_layer_identity()
    if three_layer:
        return f"{usage_preamble}\n\n{three_layer}"

    # Legacy: approved block from database
    row = conn.execute("""
        SELECT block_text, token_count, created_at, approved
        FROM identity_blocks
        WHERE approved = 1
        ORDER BY created_at DESC
        LIMIT 1
    """).fetchone()

    if row:
        return row["block_text"]

    # Fallback to latest unapproved
    row = conn.execute("""
        SELECT block_text, token_count, created_at
        FROM identity_blocks
        ORDER BY created_at DESC
        LIMIT 1
    """).fetchone()

    if row:
        return row["block_text"]

    return None


# ===========================================================================
# BLOCK 2: THEME RETRIEVAL
# ===========================================================================

def get_theme_block(conn, user_message, embed_model, chroma_client):
    """
    Retrieve theme-relevant facts for the user's message.

    Steps:
      1. Embed the user's message
      2. Search ChromaDB for similar facts (top 30)
      3. Score each: 60% semantic similarity + 40% ghost-informed importance
      4. Boost co-occurring facts (associative retrieval, D-013)
      5. Format top 15-18 facts grouped by detected topic
    """
    # Embed user message
    embedding = embed_model.encode([user_message]).tolist()

    # Search fact embeddings
    try:
        fact_collection = chroma_client.get_collection("memory_facts")
        fact_results = fact_collection.query(
            query_embeddings=embedding,
            n_results=THEME_FACTS_TO_RETRIEVE,
        )
    except Exception as e:
        print(f"  Warning: fact search failed: {e}")
        return "", []

    if not fact_results or not fact_results["ids"] or not fact_results["ids"][0]:
        return "", []

    fact_ids = fact_results["ids"][0]
    fact_distances = fact_results["distances"][0]

    from baselayer.config import chromadb_dist_to_similarity
    fact_similarities = [chromadb_dist_to_similarity(d) for d in fact_distances]

    # Fetch full fact data from SQLite
    placeholders = ",".join(["?"] * len(fact_ids))
    rows = conn.execute(
        "SELECT mf.id, mf.fact_text, mf.category, mf.confidence, mf.significance_score,"
        "       mf.recurrence_count, mf.depth_score, mf.significance_type,"
        "       mf.subject, mf.intent, mf.temporal_state, mf.sentiment,"
        "       mf.fact_class, mf.created_at,"
        "       c.created_at as conversation_date"
        " FROM memory_facts mf"
        " LEFT JOIN conversations c ON mf.source_conversation_id = c.id"
        " WHERE mf.id IN (" + placeholders + ")"
        "   AND mf.superseded_by IS NULL",
        fact_ids
    ).fetchall()

    # Build lookup
    fact_lookup = {row["id"]: row for row in rows}

    # Score each fact: 55% semantic similarity + 35% importance + 10% recency
    # Recency weighting: facts mentioned recently get a mild boost over stale ones.
    # Uses conversation date (when fact was last discussed), not extraction date.
    now = time.time()
    scored_facts = []
    for fid, similarity in zip(fact_ids, fact_similarities):
        if fid not in fact_lookup:
            continue
        row = fact_lookup[fid]
        # Importance: significance + recurrence
        sig = row["significance_score"] or 0
        rec = row["recurrence_count"] or 0
        rec_bonus = min(math.log(rec + 1) / math.log(300) * 10, 10) if rec > 0 else 0
        importance = sig * 0.7 + rec_bonus * 0.3
        importance_norm = min(importance / 10.0, 1.0)
        # Recency: decay from 1.0 (today) to 0.0 (~3 years ago)
        origin_date = row["conversation_date"] or row["created_at"] or 0
        age_days = (now - origin_date) / 86400 if origin_date else RECENCY_DECAY_WINDOW_DAYS
        recency = max(0, 1 - (age_days / RECENCY_DECAY_WINDOW_DAYS))
        blended = 0.55 * similarity + 0.35 * importance_norm + 0.10 * recency
        scored_facts.append((blended, fid, row, similarity))

    # Associative retrieval boost (D-013)
    selected_ids = set(fid for _, fid, _, _ in scored_facts[:10])  # top 10 seeds
    if selected_ids:
        assoc_placeholders = ",".join(["?"] * len(selected_ids))
        co_occurring = conn.execute(
            "SELECT fact_id_2 as related_id, co_occurrence_count"
            " FROM fact_relationships"
            " WHERE fact_id_1 IN (" + assoc_placeholders + ")"
            " UNION"
            " SELECT fact_id_1 as related_id, co_occurrence_count"
            " FROM fact_relationships"
            " WHERE fact_id_2 IN (" + assoc_placeholders + ")",
            list(selected_ids) + list(selected_ids)
        ).fetchall()

        related_ids = {r["related_id"] for r in co_occurring}

        # Apply boost to facts that co-occur with selected facts
        boosted = []
        for blended, fid, row, sim in scored_facts:
            if fid in related_ids and fid not in selected_ids:
                blended *= (1.0 + ASSOCIATIVE_BOOST)
            boosted.append((blended, fid, row, sim))
        scored_facts = boosted

    # Sort by blended score descending
    scored_facts.sort(key=lambda x: x[0], reverse=True)

    # Theme-level dedup: remove near-duplicate facts before final selection.
    # Without this, similar facts (e.g. "enjoys X" repeated in different
    # phrasings) waste ~30% of the theme token budget on redundancy.
    deduped_facts = []
    deduped_texts = []
    for item in scored_facts:
        if len(deduped_facts) >= THEME_FACTS_TO_KEEP:
            break
        fact_text = item[2]["fact_text"].lower()
        fact_words = set(fact_text.split())

        is_dup = False
        for prev_text in deduped_texts:
            prev_words = set(prev_text.split())
            overlap = len(fact_words & prev_words) / max(len(fact_words | prev_words), 1)
            if overlap > 0.40:  # 40% word overlap = too similar
                is_dup = True
                break

        if not is_dup:
            deduped_facts.append(item)
            deduped_texts.append(fact_text)

    top_facts = deduped_facts

    if not top_facts:
        return "", []

    # Group by category for readable output
    by_category = {}
    for _, fid, row, sim in top_facts:
        cat = row["category"] or "other"
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(row)

    # Format theme block
    lines = []
    # Sort categories by general identity relevance for display
    _CAT_DISPLAY_ORDER = {
        "relationship": 10, "biography": 9, "value": 9,
        "negative_trait": 8, "goal": 8, "project": 8,
        "opinion": 7, "skill": 7, "habit": 6, "preference": 6, "interest": 5,
    }
    for cat in sorted(by_category.keys(),
                      key=lambda c: _CAT_DISPLAY_ORDER.get(c, 0),
                      reverse=True):
        facts = by_category[cat]
        # Use readable category labels
        cat_labels = {
            "relationship": "People",
            "biography": "Background",
            "value": "Values",
            "negative_trait": "Growth Edges",
            "goal": "Goals",
            "opinion": "Views",
            "skill": "Skills",
            "habit": "Patterns",
            "preference": "Preferences",
            "interest": "Interests",
            "project": "Projects",
        }
        label = cat_labels.get(cat, cat.title())
        lines.append(f"## {label}")
        for f in facts:
            subject = f["subject"] or "user"
            prefix = ""
            if subject != "user":
                prefix = f"({subject}) "
            temporal = f["temporal_state"]
            try:
                fact_class = f["fact_class"] or "unclassified"
            except (IndexError, KeyError):
                fact_class = "unclassified"
            if temporal == "past":
                prefix += "[past] "

            # Temporal qualifier: state-facts get "(as of [date])" when old.
            # Uses conversation date (when fact was discussed), NOT extraction date.
            # Events are immutable — never qualified. Per TEMPORAL_PROCESSING_REVIEW V4.
            # NOTE: Currently uses source_conversation_id (single FK). For recurring
            # facts discussed across many conversations, this may show the original date
            # rather than the most recent mention. V1.1: add last_mentioned_at tracking.
            suffix = ""
            if fact_class in ("state", "unclassified") and temporal != "past":
                try:
                    origin_date = f["conversation_date"] or f["created_at"]
                except (IndexError, KeyError):
                    origin_date = None
                if origin_date:
                    try:
                        if isinstance(origin_date, (int, float)):
                            origin_dt = datetime.fromtimestamp(origin_date)
                        else:
                            origin_dt = datetime.fromisoformat(str(origin_date).replace("Z", "+00:00"))
                        age_days = (datetime.now() - origin_dt).days
                        if age_days > TEMPORAL_QUALIFIER_THRESHOLD_DAYS:
                            date_str = origin_dt.strftime("%Y-%m")
                            suffix = f" (as of {date_str})"
                    except (ValueError, TypeError, OSError):
                        pass

            lines.append(f"- {prefix}{f['fact_text']}{suffix}")
        lines.append("")

    theme_text = "\n".join(lines).strip()
    used_ids = [fid for _, fid, _, _ in top_facts]

    return theme_text, used_ids


# ===========================================================================
# BLOCK 3: EPISODE RETRIEVAL
# ===========================================================================

def get_episode_block(conn, user_message, embed_model, chroma_client):
    """
    Retrieve relevant episodic memories.

    Steps:
      1. Search conversation summaries by similarity
      2. Score: 50% similarity + 30% recency + 20% base
      3. Enrich with conversation title, date, and top facts
      4. Format as dated XML episodes
    """
    embedding = embed_model.encode([user_message]).tolist()

    # Search summary embeddings
    try:
        # Try multiple possible collection names
        summary_collection = None
        for name in ["conversation_summaries", "summary_embeddings", "summaries"]:
            try:
                summary_collection = chroma_client.get_collection(name)
                break
            except Exception:
                continue

        if summary_collection is None:
            print("  Warning: No summary collection found in ChromaDB")
            return ""

        summary_results = summary_collection.query(
            query_embeddings=embedding,
            n_results=10,
        )
    except Exception as e:
        print(f"  Warning: summary search failed: {e}")
        return ""

    if not summary_results or not summary_results["ids"] or not summary_results["ids"][0]:
        return ""

    summary_ids = summary_results["ids"][0]
    summary_distances = summary_results["distances"][0]
    summary_metas = summary_results["metadatas"][0] if summary_results.get("metadatas") else [{}] * len(summary_ids)

    from baselayer.config import chromadb_dist_to_similarity
    similarities = [chromadb_dist_to_similarity(d) for d in summary_distances]

    # Get conversation details
    scored_episodes = []
    now = time.time()

    for sid, sim, meta in zip(summary_ids, similarities, summary_metas):
        # The ID might be the conversation_id itself
        conv_id = meta.get("conversation_id", sid) if meta else sid

        conv_row = conn.execute("""
            SELECT c.id, c.title, c.created_at,
                   cs.summary
            FROM conversations c
            LEFT JOIN conversation_summaries cs ON c.id = cs.conversation_id
            WHERE c.id = ?
        """, (conv_id,)).fetchone()

        if not conv_row:
            continue

        # Recency score (0-1): more recent = higher
        age_days = (now - (conv_row["created_at"] or 0)) / 86400
        recency = max(0, 1 - (age_days / RECENCY_DECAY_WINDOW_DAYS))

        # Blended score
        score = 0.50 * sim + 0.30 * recency + 0.20

        scored_episodes.append((score, conv_row, sim))

    # Entity-aware filtering: if the user mentions a specific person/entity,
    # boost episodes that actually reference that entity and demote those that don't.
    # Prevents unrelated episodes from dominating entity-specific queries.
    # These are common life-domain categories; customize for specific corpora.
    _ENTITY_KEYWORDS = {
        "spouse": ["wife", "husband", "spouse", "partner", "wedding", "fianc", "honeymoon", "anniversary"],
        "startup": ["startup", "founded", "company"],
        "finance": ["trading", "trade", "options", "investing", "portfolio", "market"],
        "car": ["car", "drive", "driving", "vehicle"],
        "pet": ["cat", "dog", "kitten", "pet", "puppy"],
        "cooking": ["cook", "recipe", "food", "dish", "meal", "kitchen"],
    }

    msg_lower = user_message.lower()
    detected_entities = []
    for entity, keywords in _ENTITY_KEYWORDS.items():
        if any(kw in msg_lower for kw in keywords):
            detected_entities.append(entity)

    if detected_entities:
        # Get the keywords for detected entities
        entity_terms = []
        for ent in detected_entities:
            entity_terms.extend(_ENTITY_KEYWORDS[ent])

        boosted_episodes = []
        for score, conv, sim in scored_episodes:
            ep_text = ((conv["summary"] or "") + " " + (conv["title"] or "")).lower()
            # Check if episode actually mentions the entity
            entity_match = any(term in ep_text for term in entity_terms)
            if entity_match:
                score *= 1.3  # 30% boost for entity-relevant episodes
            else:
                score *= 0.7  # 30% penalty for entity-irrelevant episodes
            boosted_episodes.append((score, conv, sim))
        scored_episodes = boosted_episodes

    # Sort by score
    scored_episodes.sort(key=lambda x: x[0], reverse=True)

    # Diversity enforcement: no more than 2 episodes from the same topic.
    # Without this, the most-discussed topic dominates ambiguous queries.
    # These are common life-domain categories; customize for specific corpora.
    _TOPIC_GROUPS = {
        "finance": ["trading", "trade", "options", "market", "investing",
                     "portfolio", "stocks", "bonds", "budget"],
        "cooking": ["cook", "recipe", "food", "dish", "meal", "kitchen", "bake"],
        "cars": ["car", "drive", "wheel", "exhaust", "vehicle"],
        "career": ["job", "resume", "linkedin", "interview", "application", "hire", "role"],
        "startup": ["startup", "founded", "fundrais", "investor", "company"],
        "spouse": ["wife", "husband", "spouse", "partner", "wedding", "honeymoon", "anniversary"],
    }

    def _detect_episode_topic(conv):
        """Detect which topic group an episode belongs to."""
        import re
        text = ((conv["summary"] or "") + " " + (conv["title"] or "")).lower()
        words_in_text = set(re.findall(r'\b\w+\b', text))
        topic_scores = {}
        for topic, keywords in _TOPIC_GROUPS.items():
            # Use word-boundary matching to avoid "trade" matching inside "trading"
            hits = sum(1 for kw in keywords if kw in words_in_text or
                       (' ' in kw and kw in text))  # multi-word keywords use substring
            if hits >= 2:  # Need at least 2 distinct keyword hits
                topic_scores[topic] = hits
        if topic_scores:
            return max(topic_scores, key=topic_scores.get)
        return None

    top_episodes = []
    topic_counts = {}
    MAX_PER_TOPIC = 2

    for score, conv, sim in scored_episodes:
        if len(top_episodes) >= EPISODE_COUNT:
            break

        ep_topic = _detect_episode_topic(conv)

        # Enforce topic diversity: max 2 per topic group
        if ep_topic and topic_counts.get(ep_topic, 0) >= MAX_PER_TOPIC:
            continue

        # Also check raw word overlap as fallback for unlabeled topics
        summary_text = (conv["summary"] or "") + " " + (conv["title"] or "")
        candidate_words = set(summary_text.lower().split())
        too_similar = False
        for _, prev_conv, _ in top_episodes:
            prev_text = (prev_conv["summary"] or "") + " " + (prev_conv["title"] or "")
            prev_words = set(prev_text.lower().split())
            overlap = len(candidate_words & prev_words) / max(len(candidate_words | prev_words), 1)
            if overlap > 0.35:
                too_similar = True
                break

        if not too_similar:
            top_episodes.append((score, conv, sim))
            if ep_topic:
                topic_counts[ep_topic] = topic_counts.get(ep_topic, 0) + 1

    if not top_episodes:
        return ""

    # Batch-fetch top facts for all episodes in ONE query (fixes N+1).
    # Collect all conversation IDs, run a single query, build a lookup dict.
    episode_conv_ids = [conv["id"] for _, conv, _ in top_episodes]
    episode_facts_lookup = {}  # conv_id -> [fact_rows]
    if episode_conv_ids:
        ep_placeholders = ",".join(["?"] * len(episode_conv_ids))
        all_ep_facts = conn.execute(
            "SELECT source_conversation_id, fact_text, category, significance_score"
            " FROM memory_facts"
            " WHERE source_conversation_id IN (" + ep_placeholders + ")"
            "   AND superseded_by IS NULL"
            " ORDER BY significance_score DESC",
            episode_conv_ids
        ).fetchall()
        for row in all_ep_facts:
            cid = row["source_conversation_id"]
            if cid not in episode_facts_lookup:
                episode_facts_lookup[cid] = []
            episode_facts_lookup[cid].append(row)

    # Format as XML episodes
    lines = []
    for score, conv, sim in top_episodes:
        created = conv["created_at"]
        if created:
            date_str = datetime.fromtimestamp(created).strftime("%Y-%m-%d")
        else:
            date_str = "unknown"

        title = conv["title"] or "Untitled"
        summary = conv["summary"] or ""

        # Clean title for XML attribute
        title_clean = title.replace('"', "'").replace("&", "&amp;")[:60]

        # Get top facts from the batch lookup (already sorted by significance)
        conv_facts = episode_facts_lookup.get(conv["id"], [])[:3]

        fact_notes = ""
        if conv_facts:
            fact_items = [f["fact_text"] for f in conv_facts]
            fact_notes = " Key facts: " + "; ".join(fact_items[:2])

        # Trim summary to fit budget
        summary_trimmed = summary[:300] if summary else "No summary available."

        lines.append(f'<episode date="{date_str}" topic="{title_clean}">')
        lines.append(f"{summary_trimmed}{fact_notes}")
        lines.append("</episode>")

    return "\n".join(lines)


# ===========================================================================
# TOKEN BUDGET MANAGER
# ===========================================================================

def estimate_tokens(text: str) -> int:
    """Estimate token count from text length."""
    if not text:
        return 0
    return len(text) // CHARS_PER_TOKEN


def truncate_to_budget(text: str, token_budget: int) -> str:
    """Truncate text to fit within a token budget."""
    char_budget = token_budget * CHARS_PER_TOKEN
    if len(text) <= char_budget:
        return text

    # Truncate at last complete sentence within budget
    truncated = text[:char_budget]
    last_period = truncated.rfind(".")
    last_newline = truncated.rfind("\n")
    cut_point = max(last_period, last_newline)

    if cut_point > char_budget * 0.5:  # Only use sentence boundary if > 50% of budget
        return truncated[:cut_point + 1]
    return truncated


# ===========================================================================
# BRIEF ASSEMBLY
# ===========================================================================

BRIEF_INSTRUCTION = """You know this person. Use this context naturally — reference it when relevant, but do not recite it. If context contradicts the user, trust the user.

Identity context informs — it does not determine. People evolve. If the user presents something that doesn't match their profile, engage with what they're saying now. Do not over-apply behavioral patterns to novel situations.

Communication style: Be direct and opinionated. Give frameworks, not platitudes. Challenge over validation. Concise over exhaustive. When the answer is short, keep it short. Never coddle, never hedge everything with qualifiers. This person wants a thinking partner, not an assistant."""


def assemble_brief(conn, user_message, embed_model, chroma_client, identity_text=None):
    """
    Assemble the complete three-tier brief.

    Returns (brief_xml, metadata_dict)
    """
    start_time = time.time()

    # Overhead: instruction text + XML tags + newlines (~120 tokens).
    # Reserve this from the total budget so block budgets don't exceed the cap.
    overhead_tokens = estimate_tokens(BRIEF_INSTRUCTION) + 30  # XML tags + newlines
    available_tokens = TOTAL_TOKEN_BUDGET - overhead_tokens

    # Allocate proportionally to configured budgets
    budget_sum = IDENTITY_TOKEN_BUDGET + THEME_TOKEN_BUDGET + EPISODE_TOKEN_BUDGET
    id_budget = int(available_tokens * IDENTITY_TOKEN_BUDGET / budget_sum)
    theme_budget = int(available_tokens * THEME_TOKEN_BUDGET / budget_sum)
    ep_budget = available_tokens - id_budget - theme_budget  # remainder to episodes

    # Block 1: Identity (always-on)
    if identity_text is None:
        identity_text = get_current_identity(conn)

    if not identity_text:
        identity_text = "(Identity block not generated. Run --generate-identity first.)"

    identity_text = truncate_to_budget(identity_text, id_budget)

    # Block 2: Themes (retrieved)
    theme_text, theme_fact_ids = get_theme_block(
        conn, user_message, embed_model, chroma_client
    )
    theme_text = truncate_to_budget(theme_text, theme_budget)

    # Block 3: Episodes (retrieved)
    episode_text = get_episode_block(
        conn, user_message, embed_model, chroma_client
    )
    episode_text = truncate_to_budget(episode_text, ep_budget)

    # Assemble XML
    brief_parts = [BRIEF_INSTRUCTION, ""]

    brief_parts.append("<user_identity>")
    brief_parts.append(identity_text)
    brief_parts.append("</user_identity>")
    brief_parts.append("")

    if theme_text:
        brief_parts.append("<relevant_context>")
        brief_parts.append(theme_text)
        brief_parts.append("</relevant_context>")
        brief_parts.append("")

    if episode_text:
        brief_parts.append("<episodic_memories>")
        brief_parts.append(episode_text)
        brief_parts.append("</episodic_memories>")

    brief_xml = "\n".join(brief_parts)

    # Hard cap: if total still exceeds budget (rounding, edge cases),
    # trim episodes first, then themes. Identity is never trimmed at this stage.
    total_tokens = estimate_tokens(brief_xml)
    if total_tokens > TOTAL_TOKEN_BUDGET:
        overage = total_tokens - TOTAL_TOKEN_BUDGET
        # Try trimming episodes
        ep_current = estimate_tokens(episode_text)
        if ep_current > overage:
            episode_text = truncate_to_budget(episode_text, ep_current - overage)
        else:
            # Episodes can't absorb it all — trim themes too
            episode_text = ""
            remaining_overage = overage - ep_current
            theme_current = estimate_tokens(theme_text)
            if theme_current > remaining_overage:
                theme_text = truncate_to_budget(theme_text, theme_current - remaining_overage)

        # Reassemble after trimming
        brief_parts = [BRIEF_INSTRUCTION, ""]
        brief_parts.append("<user_identity>")
        brief_parts.append(identity_text)
        brief_parts.append("</user_identity>")
        brief_parts.append("")
        if theme_text:
            brief_parts.append("<relevant_context>")
            brief_parts.append(theme_text)
            brief_parts.append("</relevant_context>")
            brief_parts.append("")
        if episode_text:
            brief_parts.append("<episodic_memories>")
            brief_parts.append(episode_text)
            brief_parts.append("</episodic_memories>")
        brief_xml = "\n".join(brief_parts)

    # Metadata
    assembly_time = (time.time() - start_time) * 1000
    metadata = {
        "identity_tokens": estimate_tokens(identity_text),
        "theme_tokens": estimate_tokens(theme_text),
        "episode_tokens": estimate_tokens(episode_text),
        "total_tokens": estimate_tokens(brief_xml),
        "facts_used": len(theme_fact_ids),
        "assembly_time_ms": round(assembly_time, 1),
    }

    # Log assembly
    try:
        conn.execute("""
            INSERT INTO brief_assembly_log
            (user_message, identity_tokens, theme_tokens, episode_tokens,
             total_tokens, facts_used, episodes_used, assembly_time_ms, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_message[:200],
            metadata["identity_tokens"],
            metadata["theme_tokens"],
            metadata["episode_tokens"],
            metadata["total_tokens"],
            metadata["facts_used"],
            EPISODE_COUNT,
            metadata["assembly_time_ms"],
            time.time(),
        ))
        conn.commit()
    except Exception:
        pass  # Don't fail on logging

    return brief_xml, metadata


# ===========================================================================
# SESSION BUFFER (D-011)
# ===========================================================================

class SessionBuffer:
    """
    Lightweight within-session memory. Captures obvious declarations
    mid-conversation without full LLM extraction.
    """
    def __init__(self):
        self.facts = []
        self.max_facts = 10

    def scan_message(self, message: str):
        """Heuristic pattern-matching for mid-session declarations."""
        message_lower = message.lower()

        # Common declaration patterns
        patterns = [
            ("my name is ", "biography"),
            ("i just ", "event"),
            ("i started ", "event"),
            ("i'm working on ", "project"),
            ("i got ", "event"),
            ("i bought ", "event"),
            ("i moved to ", "biography"),
            ("we just ", "event"),
            ("i decided to ", "goal"),
        ]

        for pattern, category in patterns:
            if pattern in message_lower:
                # Extract the declaration (rough: rest of sentence)
                idx = message_lower.index(pattern)
                snippet = message[idx:idx + 100]
                # Trim at sentence end
                for end_char in ".!?\n":
                    end_idx = snippet.find(end_char)
                    if end_idx > 0:
                        snippet = snippet[:end_idx + 1]
                        break

                if len(snippet) > 15 and len(self.facts) < self.max_facts:
                    self.facts.append(snippet.strip())

    def get_buffer_text(self) -> str:
        """Format session buffer facts for injection into brief."""
        if not self.facts:
            return ""
        lines = ["## This Session"]
        for f in self.facts:
            lines.append(f"- {f}")
        return "\n".join(lines)


# ===========================================================================
# CLAUDE API INTEGRATION
# ===========================================================================

def call_claude(system_prompt: str, messages: list, api_key: str) -> str:
    """Call Claude API with the assembled brief as system prompt."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)  # Explicit key — cannot use singleton

        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2048,
            system=system_prompt,
            messages=messages,
        )

        return response.content[0].text
    except ImportError:
        print("ERROR: anthropic package not installed. Run: pip install anthropic")
        return None
    except Exception as e:
        print(f"ERROR calling Claude: {e}")
        return None


# ===========================================================================
# INTERACTIVE MODE
# ===========================================================================

def interactive_mode(conn, embed_model, chroma_client, api_key):
    """
    Interactive chat loop with Claude using the assembled brief.

    Commands:
      brief   — show current brief
      tokens  — show token usage
      buffer  — show session buffer
      quit    — exit
    """
    print("\n=== Interactive Mode ===")
    print("Chat with Claude using your memory brief.")
    print("Commands: brief, tokens, buffer, quit")
    print("=" * 40)

    identity_text = get_current_identity(conn)
    if not identity_text:
        print("\nWARNING: No identity block found. Run --generate-identity first.")
        print("Continuing with empty identity block.\n")

    session_buffer = SessionBuffer()
    conversation_history = []
    last_brief = None
    last_metadata = None

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        # Handle commands
        if user_input.lower() == "quit":
            print("Goodbye!")
            break
        elif user_input.lower() == "brief":
            if last_brief:
                print(f"\n--- CURRENT BRIEF ---\n{last_brief}\n--- END ---")
            else:
                print("No brief assembled yet. Send a message first.")
            continue
        elif user_input.lower() == "tokens":
            if last_metadata:
                print(f"\n  Identity: ~{last_metadata['identity_tokens']} tokens")
                print(f"  Themes:   ~{last_metadata['theme_tokens']} tokens")
                print(f"  Episodes: ~{last_metadata['episode_tokens']} tokens")
                print(f"  Total:    ~{last_metadata['total_tokens']} tokens")
                print(f"  Assembly: {last_metadata['assembly_time_ms']:.0f}ms")
            else:
                print("No brief assembled yet.")
            continue
        elif user_input.lower() == "buffer":
            buf_text = session_buffer.get_buffer_text()
            print(f"\n{buf_text}" if buf_text else "Session buffer is empty.")
            continue

        # Scan for session buffer updates
        session_buffer.scan_message(user_input)

        # Assemble brief for this message
        brief_xml, metadata = assemble_brief(
            conn, user_input, embed_model, chroma_client, identity_text
        )

        # Append session buffer to brief
        buf_text = session_buffer.get_buffer_text()
        if buf_text:
            brief_xml += f"\n\n<session_buffer>\n{buf_text}\n</session_buffer>"

        last_brief = brief_xml
        last_metadata = metadata

        # Add user message to conversation
        conversation_history.append({
            "role": "user",
            "content": user_input,
        })

        # Call Claude
        response_text = call_claude(brief_xml, conversation_history, api_key)

        if response_text:
            print(f"\nClaude: {response_text}")
            conversation_history.append({
                "role": "assistant",
                "content": response_text,
            })
        else:
            print("\n(Failed to get response from Claude)")


# ===========================================================================
# TEST MODE / EVALUATION HARNESS (D-014)
# ===========================================================================

TEST_CASES = [
    # (message, should_contain keywords, should_NOT_contain keywords)
    ("Tell me about my work style", ["focused", "analytical"], []),
    ("What's my approach to decisions?", ["evidence", "deliberate"], []),
    ("What are my interests?", ["reading", "learning"], []),
    ("Tell me about myself", [], []),
]


def run_tests(conn, embed_model, chroma_client):
    """
    Run the evaluation harness: 20 test cases scored for
    presence, absence, and efficiency.
    """
    print("\n=== Running Evaluation Harness ===\n")

    identity_text = get_current_identity(conn)
    if not identity_text:
        print("WARNING: No identity block. Run --generate-identity first.\n")

    results = []
    total_presence_hits = 0
    total_presence_possible = 0
    total_absence_hits = 0
    total_absence_possible = 0
    total_token_count = 0

    for i, (message, should_contain, should_not_contain) in enumerate(TEST_CASES, 1):
        brief_xml, metadata = assemble_brief(
            conn, message, embed_model, chroma_client, identity_text
        )

        brief_lower = brief_xml.lower()

        # Check presence
        presence_hits = 0
        presence_misses = []
        for keyword in should_contain:
            if keyword.lower() in brief_lower:
                presence_hits += 1
            else:
                presence_misses.append(keyword)

        # Check absence
        absence_hits = 0
        absence_violations = []
        for keyword in should_not_contain:
            if keyword.lower() not in brief_lower:
                absence_hits += 1
            else:
                absence_violations.append(keyword)

        total_presence_hits += presence_hits
        total_presence_possible += len(should_contain)
        total_absence_hits += absence_hits
        total_absence_possible += len(should_not_contain)
        total_token_count += metadata["total_tokens"]

        # Status
        presence_ok = presence_hits == len(should_contain) if should_contain else True
        absence_ok = absence_hits == len(should_not_contain) if should_not_contain else True
        status = "PASS" if (presence_ok and absence_ok) else "FAIL"

        if status == "FAIL":
            detail = ""
            if presence_misses:
                detail += f" missing:[{','.join(presence_misses)}]"
            if absence_violations:
                detail += f" VIOLATION:[{','.join(absence_violations)}]"
            print(f"  {status} [{i:2d}] \"{message[:50]}\"  ~{metadata['total_tokens']}tok {detail}")
        else:
            print(f"  {status} [{i:2d}] \"{message[:50]}\"  ~{metadata['total_tokens']}tok")

        results.append({
            "message": message,
            "status": status,
            "tokens": metadata["total_tokens"],
            "presence_misses": presence_misses,
            "absence_violations": absence_violations,
        })

    # Summary
    print(f"\n--- RESULTS ---")
    presence_score = total_presence_hits / total_presence_possible if total_presence_possible else 1.0
    absence_score = total_absence_hits / total_absence_possible if total_absence_possible else 1.0
    avg_tokens = total_token_count / len(TEST_CASES) if TEST_CASES else 0
    efficiency = 1.0 if avg_tokens <= TOTAL_TOKEN_BUDGET else TOTAL_TOKEN_BUDGET / avg_tokens

    passes = sum(1 for r in results if r["status"] == "PASS")
    fails = sum(1 for r in results if r["status"] == "FAIL")

    print(f"  Pass/Fail: {passes}/{fails}")
    print(f"  Presence score: {presence_score:.2f} (target >= 0.80)")
    print(f"  Absence score:  {absence_score:.2f} (target == 1.00)")
    print(f"  Avg tokens:     {avg_tokens:.0f} (budget: {TOTAL_TOKEN_BUDGET})")
    print(f"  Efficiency:     {efficiency:.2f} (target >= 0.95)")

    return results


# ===========================================================================
# MAIN
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Phase 5: Context Projection & Brief Assembly"
    )
    parser.add_argument("--generate-identity", action="store_true",
                        help="Retrieve and display cluster facts for identity block authoring")
    parser.add_argument("--store-identity", type=str, metavar="TEXT",
                        help="Store a pre-written identity block (text or @filename)")
    parser.add_argument("--approve-identity", type=int, metavar="ID",
                        help="Approve an identity block by ID")
    parser.add_argument("--show-identity", action="store_true",
                        help="Show current identity block")
    parser.add_argument("--assemble", type=str, metavar="MESSAGE",
                        help="Assemble full brief for a message")
    parser.add_argument("--show-brief", type=str, metavar="MESSAGE",
                        help="Show assembled brief (same as --assemble but formatted)")
    parser.add_argument("--interactive", action="store_true",
                        help="Interactive chat with Claude using the brief")
    parser.add_argument("--test", action="store_true",
                        help="Run 20-case evaluation harness")
    parser.add_argument("--stats", action="store_true",
                        help="Show assembly statistics")
    args = parser.parse_args()

    # Connect to database — contextlib.closing ensures conn.close() on all exit paths
    with contextlib.closing(get_db_connection()) as conn:
        create_tables(conn)

        # Commands that don't need embeddings
        if args.generate_identity:
            generate_identity_block(conn)
            return

        if args.store_identity:
            text = args.store_identity
            # Support @filename syntax: --store-identity @block.txt
            if text.startswith("@"):
                filepath = Path(text[1:])
                if not filepath.is_absolute():
                    filepath = PROJECT_ROOT / "data" / filepath
                if not filepath.exists():
                    print(f"ERROR: File not found: {filepath}")
                    return
                text = filepath.read_text(encoding="utf-8")
            store_identity_block(conn, text)
            return

        if args.approve_identity:
            with conn:
                conn.execute("""
                    UPDATE identity_blocks SET approved = 1 WHERE id = ?
                """, (args.approve_identity,))
            print(f"Identity block #{args.approve_identity} approved.")
            return

        if args.show_identity:
            text = get_current_identity(conn)
            if text:
                tokens = estimate_tokens(text)
                print(f"\n--- IDENTITY BLOCK (~{tokens} tokens) ---")
                print(text)
                print("--- END ---")
            else:
                print("No identity block found. Run --generate-identity first.")
            return

        if args.stats:
            rows = conn.execute("""
                SELECT COUNT(*) as count, AVG(total_tokens) as avg_tokens,
                       AVG(assembly_time_ms) as avg_time
                FROM brief_assembly_log
            """).fetchone()
            print(f"\n=== Assembly Statistics ===")
            print(f"  Total assemblies: {rows['count']}")
            if rows['count'] > 0:
                print(f"  Avg tokens: {rows['avg_tokens']:.0f}")
                print(f"  Avg assembly time: {rows['avg_time']:.0f}ms")

            id_rows = conn.execute("""
                SELECT id, token_count, approved, created_at
                FROM identity_blocks
                ORDER BY created_at DESC
                LIMIT 5
            """).fetchall()
            if id_rows:
                print(f"\n  Identity blocks:")
                for r in id_rows:
                    status = "APPROVED" if r["approved"] else "pending"
                    dt = datetime.fromtimestamp(r["created_at"]).strftime("%Y-%m-%d %H:%M")
                    print(f"    #{r['id']}: ~{r['token_count']} tokens, {status}, {dt}")
            return

        # Commands that need embeddings and ChromaDB
        print("Loading embedding model and ChromaDB...")
        from baselayer.api_client import get_embedding_model
        import chromadb

        embed_model = get_embedding_model()
        if embed_model is None:
            print("ERROR: Could not load embedding model. Run: pip install sentence-transformers")
            return
        chroma_client = chromadb.PersistentClient(path=str(VECTORS_DIR))
        print("  Ready.\n")

        if args.assemble or args.show_brief:
            message = args.assemble or args.show_brief
            brief_xml, metadata = assemble_brief(
                conn, message, embed_model, chroma_client
            )
            print(f"--- ASSEMBLED BRIEF ---")
            print(brief_xml)
            print(f"--- END ---\n")
            print(f"  Identity: ~{metadata['identity_tokens']} tokens")
            print(f"  Themes:   ~{metadata['theme_tokens']} tokens")
            print(f"  Episodes: ~{metadata['episode_tokens']} tokens")
            print(f"  Total:    ~{metadata['total_tokens']} tokens")
            print(f"  Facts:    {metadata['facts_used']} used")
            print(f"  Assembly: {metadata['assembly_time_ms']:.0f}ms")
            return

        if args.test:
            run_tests(conn, embed_model, chroma_client)
            return

        if args.interactive:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                print("ERROR: ANTHROPIC_API_KEY environment variable not set.")
                print("Set it with: set ANTHROPIC_API_KEY=your-key-here")
                return
            interactive_mode(conn, embed_model, chroma_client, api_key)
            return

        # No arguments — show help
        parser.print_help()


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    main()
