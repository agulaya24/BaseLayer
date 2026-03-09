"""
Vector Audit, Claim Verification, and NLI Entailment for Identity Layer Provenance.

Three mechanisms:

1. Vector Audit — embeds each claim text, queries ChromaDB for top-N
   similar facts, and compares vector-retrieved fact IDs against LLM-cited
   fact IDs. Measures topic proximity (consistency check), not causal
   derivation. Useful for exploration, not proof of provenance.

2. Claim Verification — auto-generated binary verification questions per claim.
   Types: existence, recurrence, cross_domain, temporal, contradiction,
   coverage, faithfulness.
   Executed against the live SQLite database. Deterministic and free.

3. NLI Entailment — uses DeBERTa NLI model to check whether cited facts
   logically support (entail) each claim. Answers "given these facts as
   premises, is the claim entailed?" Local model, free, ~400ms per pair.
   Measures supportability, NOT causation — a high entailment score means
   the facts are consistent with and support the claim, not that the claim
   was derived from them.

   Thresholds: entailment > 0.7 = SUPPORTED, < 0.3 = UNSUPPORTED, between = PARTIAL.

   Inherent incompleteness: NLI checks individual fact-claim pairs and
   aggregates via max (SummaC-style). It cannot assess whether facts
   *collectively* entail a synthesized claim that no single fact supports
   alone. A claim like "pattern of X across domains" may score low even
   when the underlying facts genuinely support it, because no single fact
   contains the cross-domain synthesis.

Baseline calibration note (C13):
    To interpret verification scores meaningfully, calibrate against known-good
    and known-bad layers:
      1. Run checks on current deployed layers (known-good). Record pass rates.
      2. Generate deliberately degraded layers: shuffle fact IDs in provenance
         citations, remove provenance entirely, or cite random facts.
      3. Run the same checks on degraded layers. Record pass rates.
      4. The gap between good-layer and bad-layer scores defines the
         interpretable range. A score near the good baseline is healthy;
         a score near the bad baseline indicates real problems.
    This calibration has not been implemented yet — the raw pass/fail counts
    are meaningful but the "how good is good enough" threshold is not yet
    empirically grounded.

Usage:
    from verify_provenance import vector_audit, run_verification, run_nli_verification

    # Vector audit for a layer
    results = vector_audit("ANCHORS")

    # Claim verification
    summary = run_verification("ANCHORS")

    # NLI entailment check
    nli_results = run_nli_verification("ANCHORS")

CLI: baselayer verify
     baselayer verify --nli
MCP: verify_claims tool
"""

import contextlib
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

from config import (
    DATABASE_FILE,
    VECTORS_DIR,
    ANCHORS_LAYER_FILE,
    CORE_LAYER_FILE,
    PREDICTIONS_LAYER_FILE,
    chromadb_dist_to_similarity,
    get_db,
)
from author_layers import parse_provenance_from_layer


# ==========================================================================
# CONSTANTS
# ==========================================================================

VECTOR_TOP_N = 10  # Number of similar facts to retrieve per claim
RECURRENCE_THRESHOLD = 3  # Minimum windowed_recurrence to pass recurrence check (S8: confirmed at 3)
CROSS_DOMAIN_MIN_CATEGORIES = 2  # Minimum distinct categories for cross_domain pass

# NLI entailment thresholds (Tier 2 provenance — supportability, not causation)
NLI_MODEL_NAME = "cross-encoder/nli-deberta-v3-base"  # Good balance of speed/accuracy
NLI_ENTAILMENT_SUPPORTED = 0.7    # Above this = facts support the claim
NLI_ENTAILMENT_UNSUPPORTED = 0.3  # Below this = facts do NOT support the claim
# Between UNSUPPORTED and SUPPORTED = PARTIAL (ambiguous or synthesis-dependent)

LAYER_FILES = {
    "ANCHORS": ANCHORS_LAYER_FILE,
    "CORE": CORE_LAYER_FILE,
    "PREDICTIONS": PREDICTIONS_LAYER_FILE,
}

# Fix suggestion messages by failure type (S10)
_FIX_SUGGESTIONS = {
    "existence": "Facts have been superseded. Re-author layers to use current facts.",
    "recurrence": "Low-recurrence facts cited. Consider re-authoring with higher quality threshold.",
    "cross_domain": "Claims cite facts from a single domain. Review for cross-domain evidence.",
    "temporal": "Temporal inconsistencies detected. Check cited facts for stale or contradictory temporal states.",
    "contradiction": "Internal contradictions among cited facts. Run `baselayer contradictions` then re-author.",
    "coverage": "Identity-tier facts are underrepresented in layers. Re-author to cite more identity facts.",
    "faithfulness": "Faithfulness check requires LLM verification. Enable with --faithfulness flag when ready.",
}


# ==========================================================================
# HELPERS
# ==========================================================================

def _get_layer_text(layer_name):
    """Read layer file and return the injectable block text."""
    file_path = LAYER_FILES.get(layer_name.upper())
    if not file_path or not file_path.exists():
        return None

    content = file_path.read_text(encoding="utf-8")
    marker = "## Injectable Block"
    idx = content.find(marker)
    if idx >= 0:
        return content[idx + len(marker):]
    sep = content.find("\n---\n")
    if sep >= 0:
        return content[sep + 5:]
    return content


# C14: Module-level cache for ChromaDB client and collection (singleton pattern)
_chroma_client = None
_chroma_facts_collection = None


def _get_chroma_facts_collection():
    """Get the memory_facts ChromaDB collection.

    Uses a module-level cache so repeated calls reuse the same
    PersistentClient and collection instance (similar to api_client.py
    singleton pattern). Call _reset_chroma_cache() to force reload.
    """
    global _chroma_client, _chroma_facts_collection

    if _chroma_facts_collection is not None:
        return _chroma_facts_collection

    try:
        import chromadb
    except ImportError:
        return None

    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=str(VECTORS_DIR))

    try:
        _chroma_facts_collection = _chroma_client.get_collection("memory_facts")
        return _chroma_facts_collection
    except (ValueError, RuntimeError):
        return None


def _reset_chroma_cache():
    """Reset the ChromaDB singleton cache. Useful for testing."""
    global _chroma_client, _chroma_facts_collection
    _chroma_client = None
    _chroma_facts_collection = None


def _ensure_claim_verification_table(conn):
    """Create the claim_verification table if it does not exist.

    NOTE (S5): The canonical schema for this table lives in init_database.py.
    This CREATE TABLE IF NOT EXISTS is a safety net for environments where
    init_database has not been run (e.g., development, testing).
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS claim_verification (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            claim_id TEXT NOT NULL,
            layer_name TEXT NOT NULL,
            verification_type TEXT NOT NULL,
            question TEXT NOT NULL,
            result INTEGER,
            evidence TEXT,
            verified_at REAL,
            layer_version TEXT,
            cycle_id TEXT
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_verification_claim
            ON claim_verification(layer_name, claim_id)
    """)


# ==========================================================================
# A. VECTOR AUDIT (topic proximity check, not provenance proof)
# ==========================================================================

def vector_audit(layer_name: str, top_n: int | None = None,
                 claim_id_filter: str | None = None) -> list[dict]:
    """Audit provenance via vector similarity (topic proximity).

    NOTE: This measures whether cited facts are semantically near the claim
    text. It is a consistency check, NOT proof of causal derivation. Two
    facts about the same topic will score high regardless of whether one
    informed the other. Use claim verification for deterministic checks.

    For each claim in a layer:
      1. Embed the claim text
      2. Query ChromaDB for top-N similar facts
      3. Compare vector-retrieved fact IDs against LLM-cited fact IDs
      4. Calculate citation_recall (cited found in vector) and
         vector_precision (vector hits that were cited)
      5. Store vector-based provenance entries with link_method='vector'

    Args:
        layer_name: One of ANCHORS, CORE, PREDICTIONS.
        top_n: Number of similar facts to retrieve per claim (default VECTOR_TOP_N).
        claim_id_filter: Optional claim ID (e.g. "A1") to audit only that claim.

    Returns:
        List of dicts: [{claim_id, claim_text, cited_ids, vector_ids,
                         overlap_ids, citation_recall, vector_precision}]
    """
    if top_n is None:
        top_n = VECTOR_TOP_N

    layer_name = layer_name.upper()
    layer_text = _get_layer_text(layer_name)
    if not layer_text:
        print(f"  No layer file found for {layer_name}")
        return []

    # Parse claims and their cited facts from the layer
    provenance_entries = parse_provenance_from_layer(layer_name, layer_text)
    if not provenance_entries:
        print(f"  No provenance citations found in {layer_name} layer")
        return []

    # S6: Filter to specific claim if requested
    if claim_id_filter:
        provenance_entries = [
            e for e in provenance_entries
            if e["claim_id"].upper() == claim_id_filter.upper()
        ]
        if not provenance_entries:
            print(f"  No provenance entry found for claim {claim_id_filter} in {layer_name}")
            return []

    # Load embedding model
    from api_client import get_embedding_model, embed_texts
    model = get_embedding_model()
    if model is None:
        print("  Embedding model not available")
        return []

    # Get ChromaDB facts collection
    collection = _get_chroma_facts_collection()
    if collection is None:
        print("  ChromaDB memory_facts collection not found")
        return []

    results = []
    vector_provenance_entries = []

    for entry in provenance_entries:
        claim_id = entry["claim_id"]
        claim_text = entry.get("claim_text", "")
        cited_ids = set(entry["fact_ids"])

        if not claim_text:
            results.append({
                "claim_id": claim_id,
                "claim_text": "",
                "cited_ids": list(cited_ids),
                "vector_ids": [],
                "overlap_ids": [],
                "citation_recall": 0.0,
                "vector_precision": 0.0,
            })
            continue

        # Embed the claim text
        embedding = model.encode([claim_text], show_progress_bar=False).tolist()

        # Query ChromaDB for similar facts
        try:
            query_results = collection.query(
                query_embeddings=embedding,
                n_results=top_n,
            )
        except Exception as e:
            print(f"  ChromaDB query failed for {claim_id}: {e}")
            continue

        if not query_results["ids"] or not query_results["ids"][0]:
            results.append({
                "claim_id": claim_id,
                "claim_text": claim_text,
                "cited_ids": list(cited_ids),
                "vector_ids": [],
                "overlap_ids": [],
                "citation_recall": 0.0,
                "vector_precision": 0.0,
            })
            continue

        vector_ids = set(query_results["ids"][0])
        distances = query_results["distances"][0]

        # Calculate overlap
        overlap = cited_ids & vector_ids
        # citation_recall: what fraction of LLM-cited facts appear in vector top-N
        citation_recall = len(overlap) / len(cited_ids) if cited_ids else 0.0
        # vector_precision: what fraction of vector-retrieved facts were also LLM-cited
        vector_precision = len(overlap) / len(vector_ids) if vector_ids else 0.0

        results.append({
            "claim_id": claim_id,
            "claim_text": claim_text,
            "cited_ids": list(cited_ids),
            "vector_ids": list(vector_ids),
            "vector_distances": distances,
            "overlap_ids": list(overlap),
            "citation_recall": citation_recall,
            "vector_precision": vector_precision,
        })

        # Build provenance entries for vector-linked facts
        for rank, (fid, dist) in enumerate(zip(query_results["ids"][0], distances), 1):
            similarity = chromadb_dist_to_similarity(dist)
            vector_provenance_entries.append({
                "claim_id": claim_id,
                "claim_text": claim_text,
                "fact_ids": [fid],
                "similarity_score": similarity,
                "rank": rank,
            })

    # Store vector provenance in DB
    if vector_provenance_entries:
        try:
            with contextlib.closing(get_db()) as conn:
                _store_vector_provenance(
                    conn, layer_name, vector_provenance_entries
                )
        except Exception as e:
            print(f"  WARNING: Vector provenance storage failed: {e}", file=sys.stderr)

    return results


def _store_vector_provenance(conn, layer_name, entries):
    """Store vector-based provenance entries.

    Clears previous vector entries for this layer, then inserts new ones.

    NOTE (S5): The canonical schema for layer_claim_provenance lives in
    init_database.py. This CREATE TABLE IF NOT EXISTS is a safety net for
    environments where init_database has not been run.
    """
    # Ensure table exists (safety net — canonical schema in init_database.py)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS layer_claim_provenance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            layer_name TEXT NOT NULL,
            claim_id TEXT NOT NULL,
            claim_text TEXT,
            fact_id TEXT,
            link_method TEXT DEFAULT 'authoring',
            similarity_score REAL,
            rank_in_claim INTEGER,
            layer_version TEXT,
            cycle_id TEXT,
            created_at REAL,
            FOREIGN KEY (fact_id) REFERENCES memory_facts(id)
        )
    """)

    # Clear previous VECTOR entries for this layer (keep authoring entries)
    conn.execute(
        "DELETE FROM layer_claim_provenance WHERE layer_name = ? AND link_method = 'vector'",
        (layer_name,)
    )

    now = time.time()
    inserted = 0
    for entry in entries:
        for fid in entry["fact_ids"]:
            conn.execute("""
                INSERT INTO layer_claim_provenance
                (layer_name, claim_id, claim_text, fact_id, link_method,
                 similarity_score, rank_in_claim, created_at)
                VALUES (?, ?, ?, ?, 'vector', ?, ?, ?)
            """, (
                layer_name,
                entry["claim_id"],
                entry["claim_text"],
                fid,
                entry.get("similarity_score"),
                entry.get("rank"),
                now,
            ))
            inserted += 1

    conn.commit()
    print(f"  Vector provenance: {inserted} entries stored for {layer_name}")
    return inserted


# Backward compatibility alias
verify_provenance_vector = vector_audit


# ==========================================================================
# A2. VECTOR PROVENANCE GENERATOR (for layers without citation_api provenance)
# ==========================================================================
# The Citations API only fires when the model QUOTES from document blocks.
# ANCHORS and PREDICTIONS synthesize across many facts — they don't quote,
# so citation_api returns 0 results. This generator fills that gap by:
#   1. Parsing claims from layer structure (bold headers + description text)
#   2. Embedding each claim
#   3. Querying ChromaDB for top-N closest facts
#   4. Storing as link_method='vector' in layer_claim_provenance
#
# Unlike vector_audit() which validates EXISTING provenance, this GENERATES
# provenance from scratch for layers that have none.


def parse_claims_from_layer(layer_name, layer_text):
    """Parse claim blocks from layer text using structural markers.

    Unlike parse_provenance_from_layer() which requires [F-xxx] provenance
    lines, this parses claims from the STRUCTURE of the layer (bold headers,
    descriptions, detection triggers, directives).

    Works for all three layer types:
    - ANCHORS: **A1. NAME** + description + Active when
    - CORE: **M1. NAME** / **C1. NAME** + description
    - PREDICTIONS: **P1. NAME**: trigger → response + Detection + Directive

    Returns:
        List of dicts: [{claim_id, claim_text}] where claim_text is the
        full description (not just the name — the substantive content).
    """
    claims = []
    lines = layer_text.split("\n")

    current_id = None
    current_lines = []

    # Pattern: **A1. NAME**, **P2. NAME-NAME**, **C3. NAME**, **M1. NAME**
    id_pattern = re.compile(r'\*\*([APCM]\d+)\.?\s+(.+?)\*\*')

    for line in lines:
        id_match = id_pattern.search(line)
        if id_match:
            # Save previous claim
            if current_id and current_lines:
                claim_text = " ".join(current_lines).strip()
                if len(claim_text) > 20:  # Skip trivially short claims
                    claims.append({"claim_id": current_id, "claim_text": claim_text})
            # Start new claim
            current_id = id_match.group(1)
            # Include the name as part of context
            remainder = line[id_match.end():].strip()
            current_lines = [remainder] if remainder else []
        elif current_id:
            stripped = line.strip()
            # Stop collecting at section breaks or provenance lines
            if stripped.startswith("## ") and not stripped.startswith("## Injectable"):
                if current_lines:
                    claim_text = " ".join(current_lines).strip()
                    if len(claim_text) > 20:
                        claims.append({"claim_id": current_id, "claim_text": claim_text})
                current_id = None
                current_lines = []
            elif stripped.lower().startswith("provenance:"):
                continue  # Skip provenance lines, not part of the claim
            elif stripped.lower().startswith("directive:"):
                continue  # Skip directive lines — too instruction-like for embedding match
            elif stripped.lower().startswith("false positive"):
                continue  # Skip FP warnings — meta-commentary, not factual content
            elif stripped:
                current_lines.append(stripped)

    # Don't forget the last claim
    if current_id and current_lines:
        claim_text = " ".join(current_lines).strip()
        if len(claim_text) > 20:
            claims.append({"claim_id": current_id, "claim_text": claim_text})

    return claims


def _get_anchor_queries():
    """Load raw anchor text from epistemic_anchors table for ANCHORS queries.

    Raw axiom text (e.g., "Reality is knowable and coherent...") is much
    closer to fact language than the generated directive text, yielding
    dramatically better embedding similarity with ChromaDB facts.

    Returns:
        List of dicts: [{claim_id: "A1", query_text: "...", claim_text: "..."}]
        where query_text is the raw anchor text used for embedding,
        and claim_text is the generated layer text for display.
    """
    try:
        with contextlib.closing(get_db()) as conn:
            rows = conn.execute(
                "SELECT anchor_number, anchor_text FROM epistemic_anchors "
                "WHERE status IN ('active', 'confirmed', 'confirmed_flagged') "
                "ORDER BY anchor_number"
            ).fetchall()
            if not rows:
                return None
            return [
                {"claim_id": f"A{r[0]}", "query_text": r[1]}
                for r in rows
            ]
    except Exception:
        return None


def generate_vector_provenance(layer_name, top_n=None, min_similarity=0.0):
    """Generate vector-based provenance for a layer from scratch.

    For layers where citation_api returns 0 results (ANCHORS, PREDICTIONS),
    this function:
      1. Gets query text appropriate to the layer type:
         - ANCHORS: raw axiom text from epistemic_anchors table (declarative,
           matches fact language). Falls back to parsed layer text.
         - PREDICTIONS/CORE: pattern + detection text from layer (directives
           stripped — too instruction-like for embedding match).
      2. Embeds each query using MiniLM
      3. Queries ChromaDB for the top-N closest facts
      4. Stores results as link_method='vector' in layer_claim_provenance

    Unlike vector_audit() which validates existing provenance, this CREATES
    provenance where none exists.

    min_similarity defaults to 0 — all top-N results are kept. Relative
    ranking is correct even when absolute similarity is low (directive/axiom
    text is stylistically distant from "user predicate object" facts).

    Args:
        layer_name: One of ANCHORS, CORE, PREDICTIONS.
        top_n: Number of similar facts per claim (default VECTOR_TOP_N).
        min_similarity: Minimum cosine similarity to include (default 0.0).

    Returns:
        List of dicts with claim_id, claim_text, fact_ids, similarities.
        Empty list on failure.
    """
    if top_n is None:
        top_n = VECTOR_TOP_N

    layer_name = layer_name.upper()
    layer_text = _get_layer_text(layer_name)
    if not layer_text:
        print(f"  No layer file found for {layer_name}")
        return []

    # Parse claims from layer structure (for claim_text display + fallback queries)
    claims = parse_claims_from_layer(layer_name, layer_text)
    if not claims:
        print(f"  No claims parsed from {layer_name} layer")
        return []
    print(f"  Parsed {len(claims)} claims from {layer_name} layer")

    # For ANCHORS: use raw anchor text from DB as query (much better embedding match)
    anchor_queries = None
    if layer_name == "ANCHORS":
        anchor_queries = _get_anchor_queries()
        if anchor_queries:
            print(f"  Using {len(anchor_queries)} raw anchor texts for embedding queries")

    # Load embedding model
    from api_client import get_embedding_model
    model = get_embedding_model()
    if model is None:
        print("  Embedding model not available")
        return []

    # Get ChromaDB facts collection
    collection = _get_chroma_facts_collection()
    if collection is None:
        print("  ChromaDB memory_facts collection not found")
        return []

    results = []
    vector_provenance_entries = []

    for claim in claims:
        claim_id = claim["claim_id"]
        claim_text = claim["claim_text"]

        # Choose the best query text for embedding
        query_text = claim_text  # default: parsed layer text
        if anchor_queries:
            # Match anchor query by claim_id (A1, A2, etc.)
            match = next((aq for aq in anchor_queries if aq["claim_id"] == claim_id), None)
            if match:
                query_text = match["query_text"]

        # Embed the query
        embedding = model.encode([query_text], show_progress_bar=False).tolist()

        # Query ChromaDB
        try:
            query_results = collection.query(
                query_embeddings=embedding,
                n_results=top_n,
            )
        except Exception as e:
            print(f"  ChromaDB query failed for {claim_id}: {e}")
            continue

        if not query_results["ids"] or not query_results["ids"][0]:
            continue

        fact_ids = []
        similarities = []
        for fid, dist in zip(query_results["ids"][0], query_results["distances"][0]):
            sim = chromadb_dist_to_similarity(dist)
            if sim >= min_similarity:
                fact_ids.append(fid)
                similarities.append(round(sim, 4))

        if fact_ids:
            results.append({
                "claim_id": claim_id,
                "claim_text": claim_text[:120],
                "fact_ids": fact_ids,
                "similarities": similarities,
            })

            # Build entries for storage
            for rank, (fid, sim) in enumerate(zip(fact_ids, similarities), 1):
                vector_provenance_entries.append({
                    "claim_id": claim_id,
                    "claim_text": claim_text[:120],
                    "fact_ids": [fid],
                    "similarity_score": sim,
                    "rank": rank,
                })

    # Store in DB
    if vector_provenance_entries:
        try:
            with contextlib.closing(get_db()) as conn:
                _store_vector_provenance(conn, layer_name, vector_provenance_entries)
        except Exception as e:
            print(f"  WARNING: Vector provenance storage failed: {e}", file=sys.stderr)

    # Summary
    total_links = sum(len(r["fact_ids"]) for r in results)
    print(f"  Vector provenance generated for {layer_name}: {len(results)} claims, {total_links} fact links")
    if results:
        avg_sim = sum(s for r in results for s in r["similarities"]) / total_links if total_links else 0
        print(f"  Average similarity: {avg_sim:.3f}")

    return results


# ==========================================================================
# B. CLAIM VERIFICATION
# ==========================================================================

def generate_verification_questions(layer_name: str) -> list[dict]:
    """Generate binary verification questions for each claim in a layer.

    For each claim's cited facts, generates checks:
      - existence: Is fact F-xxx active (not superseded)?
      - recurrence: Does fact F-xxx have windowed_recurrence >= threshold?
      - cross_domain: Do cited facts span >= 2 different categories?
      - temporal: Are temporal qualifiers consistent (no future-tense states,
        no contradictory current/past for same predicate)?
      - contradiction: Any superseded_by relationships among cited facts?

    Args:
        layer_name: One of ANCHORS, CORE, PREDICTIONS.

    Returns:
        List of dicts: [{claim_id, layer_name, verification_type, question}]
    """
    layer_name = layer_name.upper()
    layer_text = _get_layer_text(layer_name)
    if not layer_text:
        return []

    provenance_entries = parse_provenance_from_layer(layer_name, layer_text)
    if not provenance_entries:
        return []

    questions = []

    for entry in provenance_entries:
        claim_id = entry["claim_id"]
        fact_ids = entry["fact_ids"]

        if not fact_ids:
            continue

        # existence: one question per cited fact
        for fid in fact_ids:
            questions.append({
                "claim_id": claim_id,
                "layer_name": layer_name,
                "verification_type": "existence",
                "question": f"Is fact F-{fid} active (not superseded)?",
                "fact_ids": [fid],
            })

        # recurrence: one question per cited fact
        for fid in fact_ids:
            questions.append({
                "claim_id": claim_id,
                "layer_name": layer_name,
                "verification_type": "recurrence",
                "question": f"Does fact F-{fid} have windowed_recurrence >= {RECURRENCE_THRESHOLD}?",
                "fact_ids": [fid],
            })

        # cross_domain: one question per claim
        questions.append({
            "claim_id": claim_id,
            "layer_name": layer_name,
            "verification_type": "cross_domain",
            "question": f"Do cited facts for {claim_id} span >= {CROSS_DOMAIN_MIN_CATEGORIES} distinct categories?",
            "fact_ids": fact_ids,
        })

        # temporal: one question per claim
        questions.append({
            "claim_id": claim_id,
            "layer_name": layer_name,
            "verification_type": "temporal",
            "question": f"Are temporal qualifiers for {claim_id}'s cited facts consistent (no contradictory timestamps)?",
            "fact_ids": fact_ids,
        })

        # contradiction: one question per claim
        questions.append({
            "claim_id": claim_id,
            "layer_name": layer_name,
            "verification_type": "contradiction",
            "question": f"Are any cited facts for {claim_id} superseded by each other?",
            "fact_ids": fact_ids,
        })

    return questions


def run_verification(layer_name: str, claim_id_filter: str | None = None) -> dict:
    """Execute all verification questions against the live DB.

    Generates questions, runs each check, and stores results in
    the claim_verification table.

    Args:
        layer_name: One of ANCHORS, CORE, PREDICTIONS, or "all".
        claim_id_filter: Optional claim ID to verify (e.g. "A1"). If None, all claims.

    Returns:
        Dict with summary: {total, passed, failed, warned, by_type: {type: {passed, failed, warned}}}
    """
    if layer_name.upper() == "ALL":
        layers = ["ANCHORS", "CORE", "PREDICTIONS"]
    else:
        layers = [layer_name.upper()]

    all_questions = []
    for lname in layers:
        qs = generate_verification_questions(lname)
        all_questions.extend(qs)

    if claim_id_filter:
        all_questions = [
            q for q in all_questions
            if q["claim_id"].upper() == claim_id_filter.upper()
        ]

    if not all_questions:
        return {"total": 0, "passed": 0, "failed": 0, "warned": 0, "by_type": {}, "results": []}

    results = []
    summary = {"total": 0, "passed": 0, "failed": 0, "warned": 0, "by_type": {}, "results": []}

    with contextlib.closing(get_db()) as conn:
        _ensure_claim_verification_table(conn)

        # Clear previous results for these layers
        for lname in layers:
            if claim_id_filter:
                conn.execute(
                    "DELETE FROM claim_verification WHERE layer_name = ? AND claim_id = ?",
                    (lname, claim_id_filter.upper()),
                )
            else:
                conn.execute(
                    "DELETE FROM claim_verification WHERE layer_name = ?",
                    (lname,),
                )

        now = time.time()

        for q in all_questions:
            vtype = q["verification_type"]
            fact_ids = q["fact_ids"]
            result_val = None
            evidence = ""

            if vtype == "existence":
                result_val, evidence = _check_existence(conn, fact_ids[0])
            elif vtype == "recurrence":
                result_val, evidence = _check_recurrence(conn, fact_ids[0])
            elif vtype == "cross_domain":
                result_val, evidence = _check_cross_domain(conn, fact_ids)
            elif vtype == "temporal":
                result_val, evidence = _check_temporal(conn, fact_ids)
            elif vtype == "contradiction":
                result_val, evidence = _check_contradiction(conn, fact_ids)

            # Store result
            conn.execute("""
                INSERT INTO claim_verification
                (claim_id, layer_name, verification_type, question, result,
                 evidence, verified_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                q["claim_id"],
                q["layer_name"],
                vtype,
                q["question"],
                result_val,
                evidence,
                now,
            ))

            result_entry = {
                "claim_id": q["claim_id"],
                "layer_name": q["layer_name"],
                "verification_type": vtype,
                "question": q["question"],
                "result": result_val,
                "evidence": evidence,
            }
            results.append(result_entry)

            # Tally — result_val: 1=pass, 0=fail, -1=warn
            summary["total"] += 1
            if result_val == 1:
                summary["passed"] += 1
            elif result_val == 0:
                summary["failed"] += 1
            elif result_val == -1:
                summary["warned"] += 1

            if vtype not in summary["by_type"]:
                summary["by_type"][vtype] = {"passed": 0, "failed": 0, "warned": 0}
            if result_val == 1:
                summary["by_type"][vtype]["passed"] += 1
            elif result_val == 0:
                summary["by_type"][vtype]["failed"] += 1
            elif result_val == -1:
                summary["by_type"][vtype]["warned"] += 1

        conn.commit()

    summary["results"] = results
    return summary


# ==========================================================================
# INDIVIDUAL VERIFICATION CHECKS
# ==========================================================================

def _check_existence(conn, fact_id):
    """Check if a fact is active (not superseded).

    Returns (1, evidence) for pass, (0, evidence) for fail.
    """
    row = conn.execute(
        "SELECT id, superseded_by, fact_text FROM memory_facts WHERE id = ?",
        (fact_id,)
    ).fetchone()

    if not row:
        return 0, f"Fact {fact_id} not found in database"

    if row["superseded_by"]:
        return 0, f"Fact {fact_id} superseded by {row['superseded_by']}"

    return 1, f"Fact {fact_id} is active"


def _check_recurrence(conn, fact_id):
    """Check if a fact has sufficient recurrence.

    Checks windowed_recurrence first, falls back to recurrence_count.
    Returns (1, evidence) for pass, (0, evidence) for fail.
    """
    row = conn.execute(
        "SELECT id, recurrence_count, fact_text FROM memory_facts WHERE id = ?",
        (fact_id,)
    ).fetchone()

    if not row:
        return 0, f"Fact {fact_id} not found"

    # Try windowed_recurrence column if it exists
    rec = row["recurrence_count"] or 0
    try:
        wr_row = conn.execute(
            "SELECT windowed_recurrence FROM memory_facts WHERE id = ?",
            (fact_id,)
        ).fetchone()
        if wr_row and wr_row["windowed_recurrence"] is not None:
            rec = wr_row["windowed_recurrence"]
    except Exception:
        pass  # Column doesn't exist yet

    if rec >= RECURRENCE_THRESHOLD:
        return 1, f"Fact {fact_id} recurrence={rec} (threshold={RECURRENCE_THRESHOLD})"
    else:
        return 0, f"Fact {fact_id} recurrence={rec} < threshold={RECURRENCE_THRESHOLD}"


def _check_cross_domain(conn, fact_ids):
    """Check if cited facts span multiple categories.

    Returns (1, evidence) for pass, (0, evidence) for fail.
    """
    if not fact_ids:
        return 0, "No fact IDs provided"

    placeholders = ",".join("?" * len(fact_ids))
    rows = conn.execute(
        f"SELECT DISTINCT category FROM memory_facts WHERE id IN ({placeholders}) AND category IS NOT NULL",
        fact_ids
    ).fetchall()

    categories = [r["category"] for r in rows]
    count = len(categories)

    if count >= CROSS_DOMAIN_MIN_CATEGORIES:
        return 1, f"Spans {count} categories: {', '.join(categories)}"
    else:
        cats_str = ', '.join(categories) if categories else 'none'
        return 0, f"Only {count} category(s): {cats_str} (need >= {CROSS_DOMAIN_MIN_CATEGORIES})"


def _check_temporal(conn, fact_ids):
    """Check temporal consistency of cited facts.

    Two checks (S7 — strengthened temporal check):
      1. Flags if any fact has temporal_state='future' (likely extraction error).
      2. Flags WARN if multiple facts share the same predicate+object but have
         contradictory temporal states (e.g., one 'current' and one 'past').
         This suggests the claim may be citing both an outdated and current
         version of the same assertion.

    Returns:
        (1, evidence) for pass — no issues.
        (0, evidence) for fail — future-tense facts found.
        (-1, evidence) for warn — contradictory temporal states on same predicate.
    """
    if not fact_ids:
        return 0, "No fact IDs provided"

    placeholders = ",".join("?" * len(fact_ids))
    rows = conn.execute(
        f"""SELECT id, temporal_state, predicate, object_text
            FROM memory_facts WHERE id IN ({placeholders})""",
        fact_ids
    ).fetchall()

    if not rows:
        return 0, "No facts found"

    # Check 1: future-tense facts (hard fail)
    future_facts = []
    temporal_states = set()
    for r in rows:
        ts = r["temporal_state"] or "unknown"
        temporal_states.add(ts)
        if ts == "future":
            future_facts.append(r["id"])

    if future_facts:
        return 0, f"Future-tense facts found (likely error): {', '.join(future_facts)}"

    # Check 2 (S7): contradictory temporal states for same predicate+object
    # Group facts by (predicate, object_text) and check for mixed temporal states
    predicate_temporal = {}  # (predicate, object_text) -> set of temporal states
    for r in rows:
        pred = r["predicate"]
        obj = r["object_text"]
        ts = r["temporal_state"] or "unknown"
        if pred and obj:  # Only check facts with structured predicate+object
            key = (pred, obj)
            if key not in predicate_temporal:
                predicate_temporal[key] = {}
            predicate_temporal[key][r["id"]] = ts

    contradictions = []
    for (pred, obj), fact_states in predicate_temporal.items():
        unique_states = set(fact_states.values()) - {"unknown"}
        # If we have both 'current' and 'past' for the same predicate+object, that's a contradiction
        if "current" in unique_states and "past" in unique_states:
            fact_detail = ", ".join(
                f"{fid}={ts}" for fid, ts in fact_states.items()
                if ts in ("current", "past")
            )
            contradictions.append(f"{pred} {obj}: {fact_detail}")

    if contradictions:
        return -1, f"Contradictory temporal states: {'; '.join(contradictions[:5])}"

    return 1, f"Temporal states: {', '.join(temporal_states)}"


def _check_contradiction(conn, fact_ids):
    """Check if any cited facts are superseded by each other.

    Returns (1, evidence) for pass (no internal contradictions),
    (0, evidence) for fail.
    """
    if not fact_ids or len(fact_ids) < 2:
        return 1, "Fewer than 2 facts; no internal contradiction possible"

    placeholders = ",".join("?" * len(fact_ids))
    id_set = set(fact_ids)

    rows = conn.execute(
        f"SELECT id, superseded_by FROM memory_facts WHERE id IN ({placeholders})",
        fact_ids
    ).fetchall()

    conflicts = []
    for r in rows:
        sup = r["superseded_by"]
        if sup and sup in id_set:
            conflicts.append(f"{r['id']} superseded by {sup}")

    if conflicts:
        return 0, f"Internal contradictions: {'; '.join(conflicts)}"

    return 1, "No internal contradictions among cited facts"


# ==========================================================================
# C. COVERAGE VERIFICATION (C11)
# ==========================================================================

def _check_coverage(layer_name: str | None = None) -> dict:
    """Check what fraction of identity-tier facts are cited by any layer claim.

    This catches the "we ignored important facts" failure mode — if only 20%
    of identity-tier facts appear in provenance, the layers may be drawing
    from too narrow a slice of the knowledge base.

    Args:
        layer_name: Optional. If provided, checks coverage for that layer only.
                    If None, checks coverage across all layers.

    Returns:
        Dict with: {identity_total, identity_cited, coverage_ratio,
                     uncited_sample: [list of up to 10 uncited fact IDs]}
    """
    with contextlib.closing(get_db()) as conn:
        # Count total identity-tier active facts
        row = conn.execute("""
            SELECT COUNT(*) as cnt FROM memory_facts
            WHERE knowledge_tier = 'identity'
            AND superseded_by IS NULL
        """).fetchone()
        identity_total = row["cnt"] if row else 0

        if identity_total == 0:
            return {
                "identity_total": 0,
                "identity_cited": 0,
                "coverage_ratio": 0.0,
                "uncited_sample": [],
            }

        # Count identity-tier facts that appear in layer_claim_provenance
        if layer_name:
            cited_row = conn.execute("""
                SELECT COUNT(DISTINCT lcp.fact_id) as cnt
                FROM layer_claim_provenance lcp
                JOIN memory_facts mf ON lcp.fact_id = mf.id
                WHERE mf.knowledge_tier = 'identity'
                AND mf.superseded_by IS NULL
                AND lcp.layer_name = ?
            """, (layer_name.upper(),)).fetchone()
        else:
            cited_row = conn.execute("""
                SELECT COUNT(DISTINCT lcp.fact_id) as cnt
                FROM layer_claim_provenance lcp
                JOIN memory_facts mf ON lcp.fact_id = mf.id
                WHERE mf.knowledge_tier = 'identity'
                AND mf.superseded_by IS NULL
            """).fetchone()

        identity_cited = cited_row["cnt"] if cited_row else 0
        coverage_ratio = identity_cited / identity_total if identity_total > 0 else 0.0

        # Get a sample of uncited identity facts (for diagnostic output)
        if layer_name:
            uncited_rows = conn.execute("""
                SELECT mf.id FROM memory_facts mf
                WHERE mf.knowledge_tier = 'identity'
                AND mf.superseded_by IS NULL
                AND mf.id NOT IN (
                    SELECT DISTINCT fact_id FROM layer_claim_provenance
                    WHERE layer_name = ?
                )
                LIMIT 10
            """, (layer_name.upper(),)).fetchall()
        else:
            uncited_rows = conn.execute("""
                SELECT mf.id FROM memory_facts mf
                WHERE mf.knowledge_tier = 'identity'
                AND mf.superseded_by IS NULL
                AND mf.id NOT IN (
                    SELECT DISTINCT fact_id FROM layer_claim_provenance
                )
                LIMIT 10
            """).fetchall()

        uncited_sample = [r["id"] for r in uncited_rows]

    return {
        "identity_total": identity_total,
        "identity_cited": identity_cited,
        "coverage_ratio": coverage_ratio,
        "uncited_sample": uncited_sample,
    }


# ==========================================================================
# D. FAITHFULNESS CHECK PLACEHOLDER (C12)
# ==========================================================================

def _check_faithfulness(claim_id: str, claim_text: str,
                        fact_ids: list[str]) -> dict:
    """Check whether a claim faithfully represents its cited facts.

    PLACEHOLDER — not yet implemented. Requires an LLM call (Haiku recommended)
    to judge whether the claim text is a faithful synthesis of the cited facts.
    Enable with --faithfulness flag when ready.

    The implementation would:
      1. Retrieve fact_text for each cited fact_id
      2. Prompt Haiku: "Given these facts: [facts]. Does this claim faithfully
         represent them? [claim_text]. Answer YES/NO with a brief explanation."
      3. Return {result: 1/0, evidence: LLM explanation, cost: estimated_cost}

    Args:
        claim_id: The claim identifier (e.g. "A1", "P3").
        claim_text: The full text of the claim.
        fact_ids: List of cited fact IDs.

    Returns:
        Dict with placeholder result: {claim_id, result, evidence, verification_type}
    """
    return {
        "claim_id": claim_id,
        "verification_type": "faithfulness",
        "result": None,  # None = not evaluated
        "evidence": "Faithfulness check not yet implemented. Requires LLM call (Haiku). "
                    "Enable with --faithfulness flag when ready.",
    }


# ==========================================================================
# E. NLI ENTAILMENT VERIFICATION (Tier 2 — supportability check)
# ==========================================================================
# Uses DeBERTa NLI to check: "given fact X as premise, is claim Y entailed?"
# Measures whether cited facts logically support the claim text.
# NOT causation — high entailment means the claim is consistent with the facts,
# not that it was derived from them.
#
# Aggregation: SummaC-style max entailment across individual facts per claim.
# This is appropriate because a claim only needs ONE supporting fact to be
# considered supported (unlike contradiction detection which needs ALL to agree).

_nli_model = None


def _get_nli_model():
    """Get the NLI cross-encoder model (lazy-loaded singleton).

    Uses module-level caching (same pattern as _chroma_client). The model
    is only loaded when first needed (~400MB download on first use, ~2s load).

    Returns:
        CrossEncoder model instance, or None if dependencies unavailable.
    """
    global _nli_model
    if _nli_model is not None:
        return _nli_model

    try:
        from sentence_transformers import CrossEncoder
    except ImportError:
        print(
            "  WARNING: sentence-transformers not installed. NLI verification unavailable.\n"
            "  Install with: pip install sentence-transformers",
            file=sys.stderr,
        )
        return None

    try:
        _nli_model = CrossEncoder(NLI_MODEL_NAME)
        return _nli_model
    except Exception as e:
        print(
            f"  WARNING: Failed to load NLI model ({NLI_MODEL_NAME}): {e}\n"
            f"  NLI verification will be skipped.",
            file=sys.stderr,
        )
        return None


def _reset_nli_cache():
    """Reset the NLI model singleton cache. Useful for testing."""
    global _nli_model
    _nli_model = None


def nli_entailment_check(claim_text: str, fact_texts: list[dict]) -> dict:
    """Check whether cited facts entail (logically support) a claim via NLI.

    For each cited fact, runs NLI inference with:
        premise = fact_text
        hypothesis = claim_text

    This answers: "If the fact is true, does the claim follow?"

    NOTE: This measures supportability, NOT causation. A high score means
    the facts are semantically consistent with and support the claim. It
    does not prove the claim was derived from these facts. Synthesis claims
    (e.g., "pattern across domains") may score low because no single fact
    contains the cross-domain insight — this is an inherent limitation of
    pairwise NLI.

    Args:
        claim_text: The claim to check (hypothesis).
        fact_texts: List of dicts with keys 'fact_id' and 'fact_text'.

    Returns:
        Dict with:
            per_fact: [{fact_id, entailment, contradiction, neutral}]
            aggregate_entailment: float (max entailment across facts, SummaC-style)
            aggregate_contradiction: float (max contradiction across facts)
            verdict: "SUPPORTED" | "PARTIAL" | "UNSUPPORTED"
    """
    model = _get_nli_model()
    if model is None:
        return {
            "per_fact": [],
            "aggregate_entailment": 0.0,
            "aggregate_contradiction": 0.0,
            "verdict": "SKIPPED",
            "error": "NLI model not available",
        }

    if not claim_text or not fact_texts:
        return {
            "per_fact": [],
            "aggregate_entailment": 0.0,
            "aggregate_contradiction": 0.0,
            "verdict": "SKIPPED",
            "error": "No claim text or no facts provided",
        }

    # Build premise-hypothesis pairs
    pairs = []
    valid_facts = []
    for ft in fact_texts:
        text = ft.get("fact_text", "")
        if text:
            pairs.append((text, claim_text))
            valid_facts.append(ft)

    if not pairs:
        return {
            "per_fact": [],
            "aggregate_entailment": 0.0,
            "aggregate_contradiction": 0.0,
            "verdict": "SKIPPED",
            "error": "No valid fact texts to check",
        }

    # Run NLI inference
    # DeBERTa NLI outputs logits for [contradiction, entailment, neutral]
    # crossencoder predict returns scores — use predict with apply_softmax
    try:
        import numpy as np
        scores = model.predict(pairs, apply_softmax=True)
        # Ensure 2D: if single pair, predict may return 1D
        if scores.ndim == 1:
            scores = scores.reshape(1, -1)
    except Exception as e:
        return {
            "per_fact": [],
            "aggregate_entailment": 0.0,
            "aggregate_contradiction": 0.0,
            "verdict": "SKIPPED",
            "error": f"NLI inference failed: {e}",
        }

    # DeBERTa NLI label order: [contradiction, entailment, neutral]
    per_fact = []
    max_entailment = 0.0
    max_contradiction = 0.0

    for i, ft in enumerate(valid_facts):
        contradiction_score = float(scores[i][0])
        entailment_score = float(scores[i][1])
        neutral_score = float(scores[i][2])

        per_fact.append({
            "fact_id": ft["fact_id"],
            "entailment": entailment_score,
            "contradiction": contradiction_score,
            "neutral": neutral_score,
        })

        if entailment_score > max_entailment:
            max_entailment = entailment_score
        if contradiction_score > max_contradiction:
            max_contradiction = contradiction_score

    # Verdict based on aggregate (max) entailment
    if max_entailment >= NLI_ENTAILMENT_SUPPORTED:
        verdict = "SUPPORTED"
    elif max_entailment < NLI_ENTAILMENT_UNSUPPORTED:
        verdict = "UNSUPPORTED"
    else:
        verdict = "PARTIAL"

    return {
        "per_fact": per_fact,
        "aggregate_entailment": max_entailment,
        "aggregate_contradiction": max_contradiction,
        "verdict": verdict,
    }


def run_nli_verification(layer_name: str,
                         claim_id_filter: str | None = None) -> dict:
    """Run NLI entailment verification on a layer's claims.

    Parses claims from layer files, retrieves fact_text for cited fact IDs,
    and runs NLI entailment check on each claim.

    Args:
        layer_name: "ANCHORS", "CORE", "PREDICTIONS", or "all".
        claim_id_filter: Optional claim ID to verify (e.g. "A1").

    Returns:
        Dict with:
            layer_results: {layer_name: [{claim_id, claim_text, nli: nli_result}]}
            summary: {total, supported, partial, unsupported, skipped}
    """
    if layer_name.upper() == "ALL":
        layers = ["ANCHORS", "CORE", "PREDICTIONS"]
    else:
        layers = [layer_name.upper()]

    # Pre-check: can we load the NLI model?
    model = _get_nli_model()
    if model is None:
        return {
            "layer_results": {},
            "summary": {"total": 0, "supported": 0, "partial": 0,
                         "unsupported": 0, "skipped": 0,
                         "error": "NLI model not available"},
        }

    layer_results = {}
    summary = {"total": 0, "supported": 0, "partial": 0,
               "unsupported": 0, "skipped": 0}

    with contextlib.closing(get_db()) as conn:
        for lname in layers:
            layer_text = _get_layer_text(lname)
            if not layer_text:
                continue

            provenance_entries = parse_provenance_from_layer(lname, layer_text)
            if not provenance_entries:
                continue

            # Filter to specific claim if requested
            if claim_id_filter:
                provenance_entries = [
                    e for e in provenance_entries
                    if e["claim_id"].upper() == claim_id_filter.upper()
                ]

            claim_results = []
            for entry in provenance_entries:
                claim_id = entry["claim_id"]
                claim_text = entry.get("claim_text", "")
                fact_ids = entry.get("fact_ids", [])

                if not fact_ids or not claim_text:
                    claim_results.append({
                        "claim_id": claim_id,
                        "claim_text": claim_text,
                        "nli": {
                            "per_fact": [],
                            "aggregate_entailment": 0.0,
                            "aggregate_contradiction": 0.0,
                            "verdict": "SKIPPED",
                            "error": "No facts or no claim text",
                        },
                    })
                    summary["total"] += 1
                    summary["skipped"] += 1
                    continue

                # Retrieve fact_text for cited fact IDs
                placeholders = ",".join("?" * len(fact_ids))
                rows = conn.execute(
                    f"SELECT id, fact_text FROM memory_facts WHERE id IN ({placeholders})",
                    fact_ids,
                ).fetchall()

                fact_texts = [
                    {"fact_id": r["id"], "fact_text": r["fact_text"]}
                    for r in rows
                    if r["fact_text"]
                ]

                # Run NLI check
                nli_result = nli_entailment_check(claim_text, fact_texts)

                claim_results.append({
                    "claim_id": claim_id,
                    "claim_text": claim_text,
                    "nli": nli_result,
                })

                summary["total"] += 1
                verdict = nli_result.get("verdict", "SKIPPED")
                if verdict == "SUPPORTED":
                    summary["supported"] += 1
                elif verdict == "PARTIAL":
                    summary["partial"] += 1
                elif verdict == "UNSUPPORTED":
                    summary["unsupported"] += 1
                else:
                    summary["skipped"] += 1

            if claim_results:
                layer_results[lname] = claim_results

    return {
        "layer_results": layer_results,
        "summary": summary,
    }


def format_nli_results(nli_results: dict) -> str:
    """Format NLI entailment verification results for display.

    Args:
        nli_results: Output from run_nli_verification().

    Returns:
        Formatted string for terminal output.
    """
    lines = []
    summary = nli_results.get("summary", {})
    layer_results = nli_results.get("layer_results", {})

    if summary.get("error"):
        lines.append(f"\n  NLI Entailment: SKIPPED — {summary['error']}")
        return "\n".join(lines)

    total = summary.get("total", 0)
    supported = summary.get("supported", 0)
    partial = summary.get("partial", 0)
    unsupported = summary.get("unsupported", 0)
    skipped = summary.get("skipped", 0)

    lines.append(f"\n  NLI Entailment Verification (supportability, not causation)")
    lines.append(f"  Model: {NLI_MODEL_NAME}")
    lines.append(f"  {'─' * 50}")

    for lname, claims in layer_results.items():
        lines.append(f"\n    {lname}:")
        for c in claims:
            cid = c["claim_id"]
            ctext = c["claim_text"][:50] if c.get("claim_text") else "(no text)"
            nli = c["nli"]
            verdict = nli.get("verdict", "SKIPPED")
            agg_e = nli.get("aggregate_entailment", 0.0)
            agg_c = nli.get("aggregate_contradiction", 0.0)

            # Verdict indicator
            if verdict == "SUPPORTED":
                indicator = "PASS"
            elif verdict == "PARTIAL":
                indicator = "PART"
            elif verdict == "UNSUPPORTED":
                indicator = "FAIL"
            else:
                indicator = "SKIP"

            lines.append(
                f"      {cid:4s} {ctext:50s} "
                f"entail={agg_e:.2f} contra={agg_c:.2f} [{indicator}]"
            )

            # Show per-fact breakdown for unsupported or partial claims
            if verdict in ("UNSUPPORTED", "PARTIAL") and nli.get("per_fact"):
                for pf in nli["per_fact"][:5]:  # Cap at 5 per claim
                    lines.append(
                        f"            F-{pf['fact_id']:10s} "
                        f"e={pf['entailment']:.2f} c={pf['contradiction']:.2f} n={pf['neutral']:.2f}"
                    )
                if len(nli.get("per_fact", [])) > 5:
                    lines.append(f"            ... and {len(nli['per_fact']) - 5} more facts")

    # Summary
    lines.append(f"\n  {'─' * 50}")
    lines.append(
        f"  NLI Summary: {supported} supported, {partial} partial, "
        f"{unsupported} unsupported, {skipped} skipped (of {total} claims)"
    )

    # Thresholds reminder
    lines.append(
        f"  Thresholds: SUPPORTED > {NLI_ENTAILMENT_SUPPORTED}, "
        f"UNSUPPORTED < {NLI_ENTAILMENT_UNSUPPORTED}"
    )

    # Interpretation note
    if unsupported > 0:
        lines.append(
            f"\n  NOTE: {unsupported} unsupported claim(s). This may indicate:"
        )
        lines.append(
            "    - Cited facts don't contain the claim's specific assertion"
        )
        lines.append(
            "    - Claim is a synthesis across facts (no single fact entails it)"
        )
        lines.append(
            "    - Wrong facts were cited during authoring"
        )
    if partial > 0 and unsupported == 0:
        lines.append(
            f"\n  NOTE: {partial} partially-supported claim(s). Likely synthesis-dependent "
            "— individual facts support components of the claim but none fully entails it."
        )

    return "\n".join(lines)


# ==========================================================================
# COMBINED VERIFICATION (VECTOR + CLAIM)
# ==========================================================================

def run_full_verification(layer_name: str = "all",
                          claim_id_filter: str | None = None,
                          include_nli: bool = False) -> dict:
    """Run vector verification, claim verification, and optionally NLI entailment.

    Args:
        layer_name: "ANCHORS", "CORE", "PREDICTIONS", or "all".
        claim_id_filter: Optional specific claim ID to verify.
        include_nli: If True, also run NLI entailment verification.

    Returns:
        Dict with verification results. Keys: vector, claims, coverage,
        and optionally nli.
    """
    if layer_name.upper() == "ALL":
        layers = ["ANCHORS", "CORE", "PREDICTIONS"]
    else:
        layers = [layer_name.upper()]

    # Vector audit (topic proximity check) — pass claim_id_filter (S6)
    vector_results = {}
    for lname in layers:
        vr = vector_audit(lname, claim_id_filter=claim_id_filter)
        if vr:
            vector_results[lname] = vr

    # Claim verification
    claim_summary = run_verification(layer_name, claim_id_filter=claim_id_filter)

    # Coverage check (C11) — only when not filtering to a single claim
    coverage = None
    if not claim_id_filter:
        coverage = _check_coverage(
            layer_name if layer_name.upper() != "ALL" else None
        )

    result = {
        "vector": vector_results,
        "claims": claim_summary,
        "coverage": coverage,
    }

    # NLI entailment (optional, Tier 2)
    if include_nli:
        nli_results = run_nli_verification(layer_name, claim_id_filter=claim_id_filter)
        result["nli"] = nli_results

    return result


# ==========================================================================
# FORMATTING
# ==========================================================================

def format_vector_results(vector_results: dict) -> str:
    """Format vector audit results for display."""
    lines = []
    for layer_name, claims in vector_results.items():
        lines.append(f"\n  {layer_name} — Vector Audit (topic proximity, not provenance proof)")
        lines.append(f"  {'─' * 50}")

        total_recall = 0
        total_precision = 0
        count = 0
        weak_claims = []

        for c in claims:
            cited = len(c["cited_ids"])
            vectored = len(c["vector_ids"])
            overlap = len(c["overlap_ids"])
            cr = c["citation_recall"]
            vp = c["vector_precision"]
            lines.append(
                f"    {c['claim_id']:4s} {c['claim_text'][:50]:50s} "
                f"cited={cited} vec={vectored} overlap={overlap} "
                f"recall={cr:.0%} prec={vp:.0%}"
            )
            total_recall += cr
            total_precision += vp
            count += 1
            if cr < 0.5:
                weak_claims.append(c["claim_id"])

        if count > 0:
            avg_r = total_recall / count
            avg_p = total_precision / count
            lines.append(f"  {'─' * 50}")
            lines.append(f"    Average: citation_recall={avg_r:.0%} vector_precision={avg_p:.0%}")
            if weak_claims:
                lines.append(f"    ATTENTION: {len(weak_claims)} claims with weak vector support: {', '.join(weak_claims)}")

    return "\n".join(lines)


def format_claim_results(claim_summary: dict) -> str:
    """Format claim verification results for display."""
    lines = []
    total = claim_summary["total"]
    passed = claim_summary["passed"]
    failed = claim_summary["failed"]
    warned = claim_summary.get("warned", 0)

    warn_str = f", {warned} warned" if warned else ""
    lines.append(f"\n  Claim Verification: {passed}/{total} passed ({failed} failed{warn_str})")
    lines.append(f"  {'─' * 50}")

    for vtype, counts in sorted(claim_summary["by_type"].items()):
        p = counts["passed"]
        f = counts["failed"]
        w = counts.get("warned", 0)
        total_t = p + f + w
        pct = p / total_t * 100 if total_t > 0 else 0
        if f > 0:
            status = "FAIL"
        elif w > 0:
            status = "WARN"
        else:
            status = "PASS"
        warn_note = f" +{w}w" if w > 0 else ""
        lines.append(f"    {vtype:15s} {p:3d}/{total_t:3d} ({pct:5.1f}%) [{status}]{warn_note}")

    # Show failures and warnings
    failures = [r for r in claim_summary.get("results", []) if r["result"] == 0]
    warnings = [r for r in claim_summary.get("results", []) if r["result"] == -1]

    if failures:
        lines.append(f"\n  Failures ({len(failures)}):")
        for f in failures[:20]:  # Cap display at 20
            lines.append(f"    [{f['claim_id']}] {f['verification_type']}: {f['evidence'][:100]}")
        if len(failures) > 20:
            lines.append(f"    ... and {len(failures) - 20} more")

        # S10: Actionable fix suggestions based on failure types
        failure_types = set(f["verification_type"] for f in failures)
        lines.append(f"\n  Suggested fixes:")
        for ftype in sorted(failure_types):
            suggestion = _FIX_SUGGESTIONS.get(ftype)
            if suggestion:
                lines.append(f"    - {ftype}: {suggestion}")

    if warnings:
        lines.append(f"\n  Warnings ({len(warnings)}):")
        for w in warnings[:10]:
            lines.append(f"    [{w['claim_id']}] {w['verification_type']}: {w['evidence'][:100]}")
        if len(warnings) > 10:
            lines.append(f"    ... and {len(warnings) - 10} more")

        # S10: fix suggestions for warning types too
        warning_types = set(w["verification_type"] for w in warnings)
        lines.append(f"\n  Suggested fixes (warnings):")
        for wtype in sorted(warning_types):
            suggestion = _FIX_SUGGESTIONS.get(wtype)
            if suggestion:
                lines.append(f"    - {wtype}: {suggestion}")

    # Overall verdict
    lines.append(f"\n  {'─' * 50}")
    if total == 0:
        lines.append("  VERDICT: NO DATA — Run `baselayer author --generate all` to generate layers with provenance citations.")
    elif failed == 0 and warned == 0:
        lines.append("  VERDICT: PASS — All checks passed.")
    elif failed == 0 and warned > 0:
        lines.append(f"  VERDICT: PASS (with warnings) — {warned} warning(s) detected. Review recommended but not blocking.")
    elif failed <= total * 0.1:
        lines.append(f"  VERDICT: PASS (minor) — {failed} issue(s) detected but within tolerance.")
    else:
        lines.append(f"  VERDICT: ATTENTION — {failed} failures detected. Run `baselayer author --generate all` to refresh layers from current facts.")

    return "\n".join(lines)


def format_coverage_results(coverage: dict) -> str:
    """Format coverage verification results for display."""
    lines = []
    if coverage is None:
        return ""

    identity_total = coverage["identity_total"]
    identity_cited = coverage["identity_cited"]
    ratio = coverage["coverage_ratio"]

    lines.append(f"\n  Coverage: {identity_cited}/{identity_total} identity-tier facts cited ({ratio:.1%})")
    lines.append(f"  {'─' * 50}")

    if identity_total == 0:
        lines.append("    No identity-tier facts found. Run pipeline first.")
    elif ratio >= 0.5:
        lines.append(f"    Good coverage — majority of identity facts represented.")
    elif ratio >= 0.2:
        lines.append(f"    Moderate coverage — consider whether uncited facts contain important patterns.")
    else:
        lines.append(f"    Low coverage — layers may be drawing from too narrow a slice of the fact base.")

    uncited = coverage.get("uncited_sample", [])
    if uncited:
        lines.append(f"    Sample uncited fact IDs: {', '.join(uncited[:10])}")

    return "\n".join(lines)


# ==========================================================================
# MAIN (standalone execution)
# ==========================================================================

def main():
    """Run full verification and print results."""
    import argparse

    parser = argparse.ArgumentParser(description="Verify identity layer provenance")
    parser.add_argument("--layer", choices=["anchors", "core", "predictions", "all"],
                        default="all", help="Which layer to verify")
    parser.add_argument("--vector", action="store_true", help="Run vector verification only")
    parser.add_argument("--claim", type=str, help="Verify a specific claim (e.g. A1, P3)")
    parser.add_argument("--claims", action="store_true",
                        help="Run claim verification only (skip vector audit)")
    parser.add_argument("--nli", action="store_true",
                        help="Run NLI entailment verification (DeBERTa, local, ~400ms/pair)")
    args = parser.parse_args()

    layer = args.layer.upper()

    print(f"\n  Base Layer Provenance Verification")
    print(f"  {'=' * 50}")

    if args.nli:
        # NLI-only mode
        print(f"\n  Running NLI entailment verification...")
        nli_results = run_nli_verification(layer, claim_id_filter=args.claim)
        print(format_nli_results(nli_results))

    elif args.vector:
        # Vector only
        if layer == "ALL":
            layers = ["ANCHORS", "CORE", "PREDICTIONS"]
        else:
            layers = [layer]

        vector_results = {}
        for lname in layers:
            print(f"\n  Running vector verification for {lname}...")
            vr = vector_audit(lname, claim_id_filter=args.claim)
            if vr:
                vector_results[lname] = vr

        if vector_results:
            print(format_vector_results(vector_results))
        else:
            print("  No vector results (no provenance citations found)")

    elif args.claims:
        # Claims-only mode (S9: skip vector audit)
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
        # Specific claim
        print(f"\n  Verifying claim: {args.claim}")
        summary = run_verification(layer, claim_id_filter=args.claim)
        print(format_claim_results(summary))

    else:
        # Full verification
        result = run_full_verification(layer)

        if result["vector"]:
            print(format_vector_results(result["vector"]))

        print(format_claim_results(result["claims"]))

        # Coverage (C11)
        if result.get("coverage"):
            print(format_coverage_results(result["coverage"]))

    print()


if __name__ == "__main__":
    main()
