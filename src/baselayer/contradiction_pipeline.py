"""
Contradiction pipeline: state-fact consistency checks for live ingestion.

For each new state-fact: query ChromaDB for similar existing state-facts,
classify the relationship (contradiction / enrichment / coexistent /
ambiguous), then execute the judgment. Contradictions supersede the older
fact; ambiguous pairs are queued in ``probe_queue`` for review; enrichment
and coexistence take no action.

Design principles (D-036, D-038):
  - Binary Collapse Resistance: default to coexistence when unsure. True
    contradictions are rare and require direct logical incompatibility.
  - Events are immutable. Only state-facts are checked.
  - Any classification failure degrades to coexistent (no destructive
    action on uncertain signal).

Public API:
  - ``process_new_state_facts(conn, new_facts, chroma_client, embed_model)``:
    batch entry point used by live_extract. Returns a stats dict.
  - ``find_contradicting_facts(...)``: similarity-based candidate search.
  - ``classify_contradiction(new_fact, existing_fact)``: LLM classification.
  - ``execute_judgment(conn, judgment, new_fact_id, existing_fact_id)``:
    apply a classification result to the database.
  - ``detect_cascades(conn, new_event_fact)``: flag state-facts related to
    a major event for review.

Model routing: classification uses ``LLM_PROVIDER_CONFIG["contradiction"]``
from config.py (override with the BASELAYER_LLM_CONTRADICTION env var).
"""

import json
import logging
import re
import time
import uuid

from baselayer.config import (
    CONTRADICTION_SIMILARITY_THRESHOLD,
    LLM_PROVIDER_CONFIG,
    chromadb_dist_to_similarity,
)

logger = logging.getLogger("base-layer")

# ChromaDB neighbors fetched per new fact before threshold filtering.
CANDIDATE_POOL_SIZE = 10

VALID_JUDGMENTS = {"contradiction", "enrichment", "coexistent", "ambiguous"}

CLASSIFICATION_PROMPT = """Classify the relationship between these two facts about the same person.

NEW FACT: {new_fact}
EXISTING FACT: {existing_fact}

Categories:
- contradiction: These cannot both be currently true. The new fact directly supersedes the old.
  Example: "lives in NYC" vs "lives in SF": only one current residence.
- enrichment: The new fact adds detail to the existing fact without conflict.
  Example: "works at Google" vs "works as engineer at Google": compatible, more specific.
- coexistent: Both can be true simultaneously. Different aspects or domains.
  Example: "values efficiency" vs "values creativity": not in conflict.
- ambiguous: Unclear whether these conflict. Needs human review.

IMPORTANT: Default to coexistent when unsure. Most facts coexist.
True contradictions are rare. They require direct logical incompatibility.
A person holding seemingly opposing values in different contexts is NORMAL, not a contradiction.

Return ONLY a JSON object:
{{"judgment": "contradiction|enrichment|coexistent|ambiguous", "confidence": 0.0-1.0, "reasoning": "one sentence"}}"""


# ---------------------------------------------------------------------------
# Schema / table setup
# ---------------------------------------------------------------------------

def _ensure_probe_queue_table(conn):
    """Create the probe_queue table for ambiguous contradiction candidates.

    Safe to call repeatedly. created_at is set explicitly at insert time
    (no unixepoch() default; that requires SQLite 3.38+).
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS probe_queue (
            id TEXT PRIMARY KEY,
            new_fact_id TEXT NOT NULL,
            existing_fact_id TEXT NOT NULL,
            new_fact_text TEXT,
            existing_fact_text TEXT,
            reasoning TEXT,
            status TEXT DEFAULT 'pending',
            created_at REAL,
            resolved_at REAL,
            FOREIGN KEY (new_fact_id) REFERENCES memory_facts(id),
            FOREIGN KEY (existing_fact_id) REFERENCES memory_facts(id)
        )
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# Step 1: find candidate facts via ChromaDB similarity
# ---------------------------------------------------------------------------

def find_contradicting_facts(conn, new_fact: dict, chroma_client, embed_model,
                             threshold: float = CONTRADICTION_SIMILARITY_THRESHOLD) -> list[dict]:
    """Query ChromaDB for similar state-facts that may contradict new_fact.

    Filters to active state-facts only and excludes the new fact itself.
    Returns candidates above the similarity threshold, sorted descending.
    Degrades to an empty list if embeddings are unavailable.
    """
    if chroma_client is None or embed_model is None:
        return []

    fact_text = new_fact.get("fact_text", "")
    fact_id = new_fact.get("fact_id", "")
    if not fact_text:
        return []

    try:
        collection = chroma_client.get_collection("memory_facts")
    except Exception:
        logger.debug("Contradiction pipeline: memory_facts collection unavailable")
        return []

    try:
        embedding = embed_model.encode([fact_text]).tolist()
        results = collection.query(
            query_embeddings=embedding,
            n_results=CANDIDATE_POOL_SIZE,
        )
    except Exception as e:
        logger.warning("Contradiction pipeline: similarity query failed: %s", e)
        return []

    if not results.get("documents") or not results["documents"][0]:
        return []

    # Collect candidate IDs for a batch DB lookup.
    candidate_ids = []
    candidate_map = {}  # fact_id -> {fact_text, similarity}

    for doc, meta, distance in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        cand_id = (meta or {}).get("fact_id", "")
        if not cand_id or cand_id == fact_id:
            continue  # Skip self and unlabeled vectors.

        similarity = chromadb_dist_to_similarity(distance)
        if similarity < threshold:
            continue

        candidate_ids.append(cand_id)
        candidate_map[cand_id] = {"fact_text": doc, "similarity": similarity}

    if not candidate_ids:
        return []

    # Keep only active state-facts (events are immutable; superseded facts
    # are already out of play).
    placeholders = ",".join("?" for _ in candidate_ids)
    rows = conn.execute(f"""
        SELECT id, fact_class, predicate, category
        FROM memory_facts
        WHERE id IN ({placeholders})
          AND fact_class = 'state'
          AND superseded_by IS NULL
    """, candidate_ids).fetchall()

    candidates = []
    for row in rows:
        cand_id = row[0]
        info = candidate_map.get(cand_id, {})
        candidates.append({
            "fact_id": cand_id,
            "fact_text": info.get("fact_text", ""),
            "similarity": info.get("similarity", 0.0),
            "predicate": row[2],
            "category": row[3],
        })

    candidates.sort(key=lambda x: -x["similarity"])
    return candidates


# ---------------------------------------------------------------------------
# Step 2: classify the relationship
# ---------------------------------------------------------------------------

def classify_contradiction(new_fact: str, existing_fact: str) -> dict:
    """Classify the relationship between two state-facts via the LLM.

    Returns {"judgment": str, "confidence": float, "reasoning": str}.
    Any failure (API error, unparseable output, unknown judgment value)
    degrades to coexistent with confidence 0.0.
    """
    from baselayer.api_client import call_api

    prompt = CLASSIFICATION_PROMPT.format(
        new_fact=new_fact, existing_fact=existing_fact
    )

    try:
        response = call_api(
            model=LLM_PROVIDER_CONFIG["contradiction"],
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0,
            caller="contradiction_pipeline",
        )
        text = response.content[0].text.strip()
        result = None
        if text.startswith("{"):
            result = json.loads(text)
        else:
            match = re.search(r"\{[^}]+\}", text)
            if match:
                result = json.loads(match.group())
        if result and result.get("judgment") in VALID_JUDGMENTS:
            return result
        logger.warning(
            "Contradiction pipeline: unparseable classification output: %.120s", text
        )
    except Exception as e:
        logger.warning("Contradiction pipeline: classification failed: %s", e)

    # Default to coexistent on any failure (Binary Collapse Resistance).
    return {"judgment": "coexistent", "confidence": 0.0, "reasoning": "parse_error"}


# ---------------------------------------------------------------------------
# Step 3: execute the judgment
# ---------------------------------------------------------------------------

def execute_judgment(conn, judgment: dict, new_fact_id: str,
                     existing_fact_id: str) -> dict:
    """Apply a classification result: supersede, queue a probe, or no-op."""
    verdict = judgment.get("judgment", "coexistent")
    now = time.time()

    if verdict == "contradiction":
        conn.execute("""
            UPDATE memory_facts
            SET superseded_by = ?, temporal_state = 'past', updated_at = ?
            WHERE id = ?
        """, (new_fact_id, now, existing_fact_id))
        conn.commit()
        return {"action": "superseded", "superseded_fact_id": existing_fact_id}

    if verdict == "ambiguous":
        _ensure_probe_queue_table(conn)
        probe_id = str(uuid.uuid4())
        new_row = conn.execute(
            "SELECT fact_text FROM memory_facts WHERE id = ?", (new_fact_id,)
        ).fetchone()
        old_row = conn.execute(
            "SELECT fact_text FROM memory_facts WHERE id = ?", (existing_fact_id,)
        ).fetchone()
        conn.execute("""
            INSERT INTO probe_queue (id, new_fact_id, existing_fact_id,
                                     new_fact_text, existing_fact_text,
                                     reasoning, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (probe_id, new_fact_id, existing_fact_id,
              new_row[0] if new_row else "", old_row[0] if old_row else "",
              judgment.get("reasoning", ""), now))
        conn.commit()
        return {"action": "probe_queued", "probe_id": probe_id}

    # enrichment or coexistent: no action needed.
    return {"action": "no_action", "verdict": verdict}


# ---------------------------------------------------------------------------
# Step 4: batch entry point
# ---------------------------------------------------------------------------

def process_new_state_facts(conn, new_facts: list[dict], chroma_client,
                            embed_model) -> dict:
    """Process a batch of new state-facts through contradiction detection.

    Each fact dict needs at least ``fact_id``, ``fact_text``, ``fact_class``.
    Non-state facts are skipped (events are immutable). Returns a summary:
    {processed, contradictions, enrichments, coexistent, ambiguous,
    probes_queued}.
    """
    stats = {"processed": 0, "contradictions": 0, "enrichments": 0,
             "coexistent": 0, "ambiguous": 0, "probes_queued": 0}

    for fact in new_facts:
        if fact.get("fact_class") != "state":
            continue
        if not fact.get("fact_id"):
            logger.warning("Contradiction pipeline: skipping fact without fact_id")
            continue

        stats["processed"] += 1
        candidates = find_contradicting_facts(conn, fact, chroma_client, embed_model)

        for candidate in candidates:
            judgment = classify_contradiction(fact["fact_text"], candidate["fact_text"])
            verdict = judgment.get("judgment", "coexistent")

            execute_judgment(conn, judgment, fact["fact_id"], candidate["fact_id"])

            if verdict == "contradiction":
                stats["contradictions"] += 1
            elif verdict == "enrichment":
                stats["enrichments"] += 1
            elif verdict == "ambiguous":
                stats["ambiguous"] += 1
                stats["probes_queued"] += 1
            else:
                stats["coexistent"] += 1

    return stats


# ---------------------------------------------------------------------------
# Step 5: cascade detection for major events
# ---------------------------------------------------------------------------

def detect_cascades(conn, new_event_fact: dict) -> list[str]:
    """Flag state-facts related to a major event for review.

    Example: a "got divorced" event may invalidate a "married_to X" state.
    Uses fact_relationships co-occurrence links. Returns flagged fact IDs;
    no database mutation happens here.
    """
    fact_id = new_event_fact.get("fact_id", "")
    if not fact_id:
        return []

    rows = conn.execute("""
        SELECT DISTINCT f.id
        FROM memory_facts f
        JOIN fact_relationships fr
            ON (f.id = fr.fact_id_1 OR f.id = fr.fact_id_2)
        WHERE (fr.fact_id_1 = ? OR fr.fact_id_2 = ?)
          AND f.fact_class = 'state'
          AND f.superseded_by IS NULL
          AND f.id != ?
    """, (fact_id, fact_id, fact_id)).fetchall()

    return [r[0] for r in rows]
