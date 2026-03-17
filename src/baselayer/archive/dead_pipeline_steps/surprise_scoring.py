"""
Phase 4, Step 3: Surprise Scoring System (Decisions D-004, D-009, D-015, D-016)

Implements the two-axis scoring system:
  1. Novelty — embedding distance (is this different from what we already know?)
  2. Significance — data-driven recurrence + depth, confirmed by LLM

Key design principle (D-015/D-016): DATA-FIRST, LLM-SECOND.
  - Recurrence and depth metrics are computed deterministically
  - A recurrence floor auto-elevates persistent topics
  - The LLM (Qwen 2.5 14B) categorizes and refines, but doesn't override the data

Two types of significance:
  - Depth-significant: user goes deep (many turns, long messages, follow-ups)
  - Identity-significant: persistent across years even if shallow (recurrence floor)

Run: python surprise_scoring.py
     python surprise_scoring.py --conversation <conv_id>   # Score a single conversation
"""

import contextlib
import sys
import io
import sqlite3
import json
import time
import argparse
import requests
from pathlib import Path
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from config import (
    DATABASE_FILE, VECTORS_DIR, EMBEDDING_MODEL, OLLAMA_URL, LLM_MODEL,
    NOVELTY_SKIP, NOVELTY_STORE,
    RECURRENCE_FLOOR_HIGH, RECURRENCE_FLOOR_MID,
    RECURRENCE_FLOOR_HIGH_SCORE, RECURRENCE_FLOOR_MID_SCORE,
    RECURRENCE_MIN_SPAN_DAYS,
    WEIGHT_NOVELTY, WEIGHT_RECURRENCE, WEIGHT_DEPTH,
)


# ---------------------------------------------------------------------------
# Novelty Scoring (embedding distance)
# ---------------------------------------------------------------------------

def compute_novelty_score(text: str, collection) -> float:
    """
    Compute novelty as 1 - max_cosine_similarity with existing embeddings.
    High score = very different from anything we've seen (novel).
    Low score = very similar to existing content (redundant).
    """
    from api_client import get_embedding_model

    model = get_embedding_model()
    if model is None:
        return 1.0  # Cannot compute novelty without embeddings; treat as novel
    embedding = model.encode([text]).tolist()

    # Query for most similar existing content
    results = collection.query(
        query_embeddings=embedding,
        n_results=5,
    )

    if not results["distances"] or not results["distances"][0]:
        return 1.0  # Nothing to compare against = maximally novel

    from config import chromadb_dist_to_similarity
    min_distance = min(results["distances"][0])
    similarity = chromadb_dist_to_similarity(min_distance)
    novelty = 1 - similarity

    return round(novelty, 4)


# ---------------------------------------------------------------------------
# Recurrence + Depth Metrics (deterministic, no LLM)
# ---------------------------------------------------------------------------

def compute_topic_metrics(conn, keywords: list[str]) -> dict:
    """
    Compute recurrence and depth metrics for a topic across all conversations.
    This is the data-driven foundation of significance scoring.
    """
    if not keywords:
        return {"recurrence": 0, "depth_score": 0, "span_days": 0}

    # Build parameterized LIKE clauses (no SQL injection)
    like_clauses = " OR ".join(["LOWER(m.content_text) LIKE ?" for _ in keywords])
    like_params = [f"%{kw.lower()}%" for kw in keywords]

    # Get per-conversation metrics
    query = f"""
        SELECT m.conversation_id,
               COUNT(*) as user_turns,
               AVG(LENGTH(m.content_text)) as avg_msg_length,
               SUM(CASE WHEN m.content_text LIKE '%?%' THEN 1 ELSE 0 END) as questions
        FROM messages m
        WHERE m.role = 'user'
          AND ({like_clauses})
        GROUP BY m.conversation_id
    """
    rows = conn.execute(query, like_params).fetchall()

    if not rows:
        return {
            "recurrence": 0, "depth_score": 0, "span_days": 0,
            "total_turns": 0, "avg_turns": 0, "deep_convos": 0,
            "moderate_convos": 0, "shallow_convos": 0, "total_questions": 0,
            "avg_msg_length": 0, "first_mention": None, "last_mention": None,
        }

    recurrence = len(rows)
    total_turns = sum(r[1] for r in rows)
    avg_turns = total_turns / recurrence
    avg_msg_len = sum(r[2] for r in rows) / recurrence
    total_questions = sum(r[3] for r in rows)

    deep_convos = sum(1 for r in rows if r[1] >= 4)
    moderate_convos = sum(1 for r in rows if 2 <= r[1] < 4)
    shallow_convos = sum(1 for r in rows if r[1] == 1)

    # Date span
    date_query = f"""
        SELECT MIN(c.created_at), MAX(c.created_at)
        FROM messages m
        JOIN conversations c ON m.conversation_id = c.id
        WHERE m.role = 'user' AND ({like_clauses})
    """
    date_row = conn.execute(date_query, like_params).fetchone()
    first_ts = date_row[0]
    last_ts = date_row[1]
    span_days = int((last_ts - first_ts) / 86400) if first_ts and last_ts else 0

    first_mention = datetime.fromtimestamp(first_ts).strftime('%Y-%m-%d') if first_ts else None
    last_mention = datetime.fromtimestamp(last_ts).strftime('%Y-%m-%d') if last_ts else None

    # Compute depth score (0-10 scale)
    # Factors: avg turns per conversation, deep conversation ratio, question ratio
    turns_score = min(avg_turns / 4, 1.0) * 10       # 4+ avg turns = max
    depth_ratio = deep_convos / recurrence if recurrence > 0 else 0
    depth_component = depth_ratio * 10                 # 100% deep convos = max
    question_ratio = total_questions / total_turns if total_turns > 0 else 0
    question_component = min(question_ratio / 0.5, 1.0) * 10  # 50%+ questions = max
    msg_len_component = min(avg_msg_len / 300, 1.0) * 10      # 300+ avg chars = max

    depth_score = (
        turns_score * 0.30 +
        depth_component * 0.30 +
        question_component * 0.20 +
        msg_len_component * 0.20
    )

    return {
        "recurrence": recurrence,
        "depth_score": round(depth_score, 2),
        "span_days": span_days,
        "total_turns": total_turns,
        "avg_turns": round(avg_turns, 2),
        "deep_convos": deep_convos,
        "moderate_convos": moderate_convos,
        "shallow_convos": shallow_convos,
        "total_questions": total_questions,
        "avg_msg_length": round(avg_msg_len, 0),
        "first_mention": first_mention,
        "last_mention": last_mention,
    }


def apply_recurrence_floor(recurrence: int, span_days: int) -> int:
    """
    Apply the recurrence floor (D-015).
    Highly persistent topics cannot score below a minimum, regardless of depth.
    This catches identity-significant topics like cars, hobbies, etc.
    """
    if recurrence >= RECURRENCE_FLOOR_HIGH and span_days >= RECURRENCE_MIN_SPAN_DAYS:
        return RECURRENCE_FLOOR_HIGH_SCORE
    elif recurrence >= RECURRENCE_FLOOR_MID and span_days >= RECURRENCE_MIN_SPAN_DAYS:
        return RECURRENCE_FLOOR_MID_SCORE
    return 0  # No floor applies


def classify_significance_type(metrics: dict) -> str:
    """
    Classify whether a topic is depth-significant or identity-significant.
    - Depth-significant: high avg turns, lots of deep convos, many questions
    - Identity-significant: high recurrence + span, but shallow engagement
    """
    if metrics["recurrence"] == 0:
        return "unknown"

    depth_ratio = metrics["deep_convos"] / metrics["recurrence"]

    if depth_ratio >= 0.15 and metrics["avg_turns"] >= 2.0:
        return "depth"
    elif metrics["recurrence"] >= 30 and metrics["span_days"] >= 180:
        return "identity"
    elif metrics["recurrence"] >= 10:
        return "recurring"
    else:
        return "episodic"


# ---------------------------------------------------------------------------
# LLM Significance (Qwen 2.5 — categorizer, not primary judge)
# ---------------------------------------------------------------------------

def llm_categorize(fact_text: str, metrics: dict) -> dict:
    """
    Ask Qwen to categorize the fact and provide nuanced assessment.
    The LLM's role is categorization and edge-case handling, NOT primary scoring.
    It receives the data signals so it makes informed decisions.
    """
    prompt = f"""You are categorizing a fact about a user for a personal AI memory system.

Fact: "{fact_text}"

DATA FROM CONVERSATION HISTORY:
- Appears in {metrics['recurrence']} out of 1,821 conversations
- Date range: {metrics.get('first_mention', 'unknown')} to {metrics.get('last_mention', 'unknown')}
- {metrics['deep_convos']} deep conversations, {metrics['moderate_convos']} moderate, {metrics['shallow_convos']} shallow
- {metrics['total_questions']} questions asked about this topic
- Average message length: {metrics['avg_msg_length']:.0f} characters

Respond with ONLY a JSON object:
{{"category": "<preference|biography|project|relationship|interest|skill|value|habit>", "llm_score": <1-10>, "reasoning": "<one sentence>"}}"""

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": LLM_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 200},
            },
            timeout=120,
        )
        response.raise_for_status()
        raw = response.json().get("response", "").strip()

        # Handle markdown-wrapped JSON
        if "```" in raw:
            raw = raw.split("```")[1].replace("json", "").strip()

        return json.loads(raw)
    except Exception as e:
        return {"category": "unknown", "llm_score": 5, "reasoning": f"LLM error: {e}"}


# ---------------------------------------------------------------------------
# Combined Scoring
# ---------------------------------------------------------------------------

def compute_final_score(
    novelty: float,
    metrics: dict,
    llm_result: dict | None = None,
) -> dict:
    """
    Compute the final significance score using the data-first formula.

    Formula: max(recurrence_floor, weighted_score)
    Where weighted_score = 40% novelty + 35% recurrence + 25% depth

    The LLM can adjust upward but cannot lower below the recurrence floor.
    """
    recurrence = metrics["recurrence"]
    depth_score = metrics["depth_score"]
    span_days = metrics["span_days"]

    # Normalize recurrence to 0-10 scale (log scale to handle wide range)
    import math
    if recurrence > 0:
        recurrence_normalized = min(math.log(recurrence + 1) / math.log(300) * 10, 10)
    else:
        recurrence_normalized = 0

    # Compute weighted score
    novelty_component = novelty * 10  # Scale to 0-10
    weighted_score = (
        WEIGHT_NOVELTY * novelty_component +
        WEIGHT_RECURRENCE * recurrence_normalized +
        WEIGHT_DEPTH * depth_score
    )

    # Apply recurrence floor
    floor = apply_recurrence_floor(recurrence, span_days)
    significance_type = classify_significance_type(metrics)

    # LLM adjustment (optional, cannot lower below floor)
    llm_score = llm_result.get("llm_score", 5) if llm_result else 5
    category = llm_result.get("category", "unknown") if llm_result else "unknown"

    # Final score = max of floor, weighted formula, and LLM
    final_score = max(floor, weighted_score, llm_score)
    final_score = round(min(final_score, 10), 2)  # Cap at 10

    return {
        "final_score": final_score,
        "novelty": round(novelty, 4),
        "recurrence_normalized": round(recurrence_normalized, 2),
        "depth_score": depth_score,
        "weighted_score": round(weighted_score, 2),
        "recurrence_floor": floor,
        "significance_type": significance_type,
        "category": category,
        "llm_score": llm_score,
    }


# ---------------------------------------------------------------------------
# Batch Processing
# ---------------------------------------------------------------------------

def create_topic_scores_table():
    """Create table for storing computed topic scores."""
    with contextlib.closing(sqlite3.connect(DATABASE_FILE)) as conn:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS topic_scores (
                    topic TEXT PRIMARY KEY,
                    keywords TEXT,
                    recurrence INTEGER,
                    depth_score REAL,
                    span_days INTEGER,
                    significance_type TEXT,
                    recurrence_floor INTEGER,
                    novelty_score REAL,
                    weighted_score REAL,
                    llm_score REAL,
                    final_score REAL,
                    category TEXT,
                    reasoning TEXT,
                    computed_at REAL
                )
            """)


def save_topic_score(topic: str, keywords: list[str], metrics: dict, score_result: dict, reasoning: str):
    """Save a topic's computed score to SQLite."""
    with contextlib.closing(sqlite3.connect(DATABASE_FILE)) as conn:
        with conn:
            conn.execute("""
                INSERT OR REPLACE INTO topic_scores
                (topic, keywords, recurrence, depth_score, span_days, significance_type,
                 recurrence_floor, novelty_score, weighted_score, llm_score, final_score,
                 category, reasoning, computed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                topic, json.dumps(keywords), metrics["recurrence"], metrics["depth_score"],
                metrics["span_days"], score_result["significance_type"],
                score_result["recurrence_floor"], score_result["novelty"],
                score_result["weighted_score"], score_result["llm_score"],
                score_result["final_score"], score_result["category"],
                reasoning, time.time(),
            ))


def extract_topics_from_conversations(conn) -> list[dict]:
    """
    Extract candidate topics from conversation titles.
    This is a simple first pass — the fact extraction pipeline (Phase 4, Step 4)
    will do deeper extraction later.
    """
    # Get all conversation titles as a starting point
    rows = conn.execute("""
        SELECT title, COUNT(*) as count
        FROM conversations
        WHERE title IS NOT NULL AND LENGTH(title) > 3
        GROUP BY LOWER(title)
        HAVING count >= 2
        ORDER BY count DESC
        LIMIT 200
    """).fetchall()

    # Also extract frequently mentioned terms from user messages
    # (simplified — full NLP extraction comes in fact extraction step)
    print(f"  Found {len(rows)} recurring conversation titles")
    return [{"title": r[0], "count": r[1]} for r in rows]


# ---------------------------------------------------------------------------
# Main Pipeline
# ---------------------------------------------------------------------------

def score_single_topic(topic_name: str, keywords: list[str], use_llm: bool = True):
    """Score a single topic — useful for testing and live scoring."""
    with contextlib.closing(sqlite3.connect(DATABASE_FILE)) as conn:
        print(f"\nTopic: {topic_name}")
        print(f"Keywords: {keywords}")

        # Compute metrics
        metrics = compute_topic_metrics(conn, keywords)
        print(f"  Recurrence: {metrics['recurrence']} conversations")
        print(f"  Span: {metrics['span_days']} days ({metrics.get('first_mention', '?')} to {metrics.get('last_mention', '?')})")
        print(f"  Depth: {metrics['deep_convos']} deep / {metrics['moderate_convos']} mod / {metrics['shallow_convos']} shallow")
        print(f"  Depth score: {metrics['depth_score']}/10")

        # Novelty (using turn_pairs collection if available, else messages)
        import chromadb
        client = chromadb.PersistentClient(path=str(VECTORS_DIR))
        try:
            collection = client.get_collection("turn_pairs")
        except Exception:
            try:
                collection = client.get_collection("messages")
            except Exception:
                print("  No embedding collection found. Setting novelty to 0.5.")
                collection = None

        if collection:
            novelty = compute_novelty_score(topic_name, collection)
        else:
            novelty = 0.5  # Neutral if no embeddings available

        print(f"  Novelty: {novelty}")

        # LLM categorization
        llm_result = None
        if use_llm and metrics["recurrence"] > 0:
            print(f"  Asking Qwen for categorization...")
            llm_result = llm_categorize(f"The user is interested in {topic_name}.", metrics)
            print(f"  LLM: {llm_result.get('category', '?')} | Score: {llm_result.get('llm_score', '?')} | {llm_result.get('reasoning', '')}")

        # Final score
        result = compute_final_score(novelty, metrics, llm_result)
        print(f"\n  FINAL SCORE: {result['final_score']}/10")
        print(f"  Type: {result['significance_type']}")
        print(f"  Floor: {result['recurrence_floor']} | Weighted: {result['weighted_score']} | LLM: {result['llm_score']}")

    return result, metrics


def demo_scoring():
    """Run scoring on known test topics to verify the system works."""
    print("=" * 60)
    print("Surprise Scoring System — Demo Run")
    print(f"LLM: {LLM_MODEL}")
    print("=" * 60)

    # Demo topics — customize these to match topics present in your data.
    # Each tuple is (display_name, [keyword list for matching]).
    test_topics = [
        ("Technology", ["software", "programming", "code", "system"]),
        ("Finance", ["investing", "market", "budget", "portfolio"]),
        ("Health", ["exercise", "gym", "workout", "nutrition"]),
        ("Creative", ["writing", "art", "design", "music"]),
        ("Career", ["job", "career", "work", "interview"]),
    ]

    create_topic_scores_table()

    results = []
    for topic_name, keywords in test_topics:
        result, metrics = score_single_topic(topic_name, keywords, use_llm=True)
        reasoning = result.get("category", "") + ": scored via data-first pipeline"
        save_topic_score(topic_name, keywords, metrics, result, reasoning)
        results.append((topic_name, metrics["recurrence"], result))

    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    print(f"{'Topic':<25} {'Convos':>6} {'Floor':>6} {'Weighted':>9} {'LLM':>5} {'FINAL':>7} {'Type':<12}")
    print(f"{'─' * 25} {'─' * 6} {'─' * 6} {'─' * 9} {'─' * 5} {'─' * 7} {'─' * 12}")

    for topic_name, recurrence, result in results:
        print(
            f"{topic_name:<25} {recurrence:>6} "
            f"{result['recurrence_floor']:>6} {result['weighted_score']:>9.1f} "
            f"{result['llm_score']:>5} {result['final_score']:>7.1f} "
            f"{result['significance_type']:<12}"
        )


def main():
    parser = argparse.ArgumentParser(description="Surprise Scoring System")
    parser.add_argument("--demo", action="store_true", help="Run demo on test topics")
    parser.add_argument("--topic", type=str, help="Score a single topic")
    parser.add_argument("--keywords", type=str, help="Comma-separated keywords for the topic")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM categorization (faster)")

    args = parser.parse_args()

    if args.topic and args.keywords:
        keywords = [k.strip() for k in args.keywords.split(",")]
        create_topic_scores_table()
        score_single_topic(args.topic, keywords, use_llm=not args.no_llm)
    elif args.demo:
        demo_scoring()
    else:
        # Default: run demo
        demo_scoring()


if __name__ == "__main__":
    main()
