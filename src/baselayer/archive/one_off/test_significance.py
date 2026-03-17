"""
D-015 Test: Recurrence + Depth Significance Scoring
Compares blind vs data-informed judgment across multiple models.

Tests: qwen2.5:14b, qwen3:14b, llama3.1:8b
"""

import sys
import io
import contextlib
import sqlite3
import json
import time
import requests
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from config import DATABASE_FILE, OLLAMA_URL
DATABASE = str(DATABASE_FILE)

MODELS = ["qwen3:14b"]

TOPICS = [
    {
        "name": "Cars",
        "fact": "The user drives a sports car.",
        "keywords": ["car", "vehicle", "drive"],
    },
    {
        "name": "Options Trading",
        "fact": "The user trades options, focusing on theta decay strategies.",
        "keywords": ["theta", "options", "puts", "calls", "spreads", "strategies"],
    },
    {
        "name": "AI Memory System",
        "fact": "The user is building a personal AI memory system using ChromaDB and SQLite.",
        "keywords": ["memory system", "chromadb", "embeddings", "rag"],
    },
    {
        "name": "Cooking",
        "fact": "The user cooks meals at home.",
        "keywords": ["recipe", "cooking", "dinner", "meal prep"],
    },
    {
        "name": "Fitness",
        "fact": "The user works out at the gym.",
        "keywords": ["gym", "workout", "lifting", "exercise"],
    },
]


def measure_recurrence_and_depth(conn, keywords):
    """Count conversations and measure depth of engagement for a topic."""
    like_clauses = " OR ".join(["LOWER(m.content_text) LIKE ?" for _ in keywords])
    like_params = [f"%{kw.lower()}%" for kw in keywords]

    query = f"""
        SELECT m.conversation_id,
               COUNT(*) as user_turns,
               AVG(LENGTH(m.content_text)) as avg_msg_length,
               MAX(LENGTH(m.content_text)) as max_msg_length,
               SUM(CASE WHEN m.content_text LIKE '%?%' THEN 1 ELSE 0 END) as question_count
        FROM messages m
        WHERE m.role = 'user'
          AND ({like_clauses})
        GROUP BY m.conversation_id
        ORDER BY user_turns DESC
    """
    rows = conn.execute(query, like_params).fetchall()

    if not rows:
        return {"recurrence": 0}

    total_convos = len(rows)
    total_user_turns = sum(r[1] for r in rows)
    avg_turns_per_conv = total_user_turns / total_convos
    avg_msg_len = sum(r[2] for r in rows) / total_convos
    total_questions = sum(r[4] for r in rows)

    deep_convos = sum(1 for r in rows if r[1] >= 4)
    moderate_convos = sum(1 for r in rows if 2 <= r[1] < 4)
    shallow_convos = sum(1 for r in rows if r[1] == 1)

    date_query = f"""
        SELECT MIN(c.created_at), MAX(c.created_at)
        FROM messages m
        JOIN conversations c ON m.conversation_id = c.id
        WHERE m.role = 'user'
          AND ({like_clauses})
    """
    date_row = conn.execute(date_query, like_params).fetchone()
    first_mention = datetime.fromtimestamp(date_row[0]).strftime('%Y-%m-%d') if date_row[0] else "unknown"
    last_mention = datetime.fromtimestamp(date_row[1]).strftime('%Y-%m-%d') if date_row[1] else "unknown"

    return {
        "recurrence": total_convos,
        "total_user_turns": total_user_turns,
        "avg_turns_per_conv": round(avg_turns_per_conv, 1),
        "avg_msg_length": round(avg_msg_len, 0),
        "total_questions": total_questions,
        "deep_convos": deep_convos,
        "moderate_convos": moderate_convos,
        "shallow_convos": shallow_convos,
        "first_mention": first_mention,
        "last_mention": last_mention,
    }


def ask_model(model, prompt):
    """Send prompt to a model and get response."""
    start = time.time()
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 500},
            },
            timeout=180,
        )
        response.raise_for_status()
        result = response.json()
        elapsed = time.time() - start
        return result.get("response", "").strip(), elapsed
    except Exception as e:
        return f"ERROR: {e}", time.time() - start


def build_informed_prompt(fact, metrics):
    """Build the data-informed significance prompt."""
    return f"""You are evaluating facts about a user for a personal AI memory system.
Rate the significance of this fact for understanding the user long-term.

Fact: "{fact}"

DATA FROM THE USER'S CONVERSATION HISTORY:
- This topic appears in {metrics['recurrence']} out of 1,821 total conversations
- Date range: {metrics['first_mention']} to {metrics['last_mention']}
- The user made {metrics['total_user_turns']} total messages about this topic
- Average {metrics['avg_turns_per_conv']} user turns per conversation on this topic
- {metrics['deep_convos']} deep conversations (4+ turns), {metrics['moderate_convos']} moderate (2-3 turns), {metrics['shallow_convos']} shallow (1 mention)
- The user asked {metrics['total_questions']} questions about this topic
- Average message length: {metrics['avg_msg_length']:.0f} characters

Respond with ONLY a JSON object, no markdown, no explanation:
{{"score": <1-10>, "reasoning": "<one sentence>"}}"""


def strip_thinking(text):
    """Strip Qwen3's <think>...</think> tags from response."""
    import re
    # Remove everything between <think> and </think>
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
    return text


def extract_score(response_text):
    """Try to pull a numeric score from model response."""
    try:
        text = strip_thinking(response_text)
        if "```" in text:
            text = text.split("```")[1].replace("json", "").strip()
        return json.loads(text).get("score", "?")
    except (json.JSONDecodeError, ValueError, KeyError):
        # Try to find a number after "score"
        import re
        text = strip_thinking(response_text)
        match = re.search(r'"score"\s*:\s*(\d+)', text)
        if match:
            return int(match.group(1))
        return "?"


def main():
    print("=" * 70)
    print("D-015 TEST: Model Comparison — Informed Significance Scoring")
    print(f"Models: {', '.join(MODELS)}")
    print("=" * 70)

    with contextlib.closing(sqlite3.connect(DATABASE)) as conn:
        # Step 1: Measure all topic metrics once
        print("\n--- Measuring recurrence + depth for all topics ---\n")
        topic_metrics = {}
        for topic in TOPICS:
            metrics = measure_recurrence_and_depth(conn, topic["keywords"])
            topic_metrics[topic["name"]] = metrics
            print(f"  {topic['name']}: {metrics['recurrence']} convos | "
                  f"{metrics['deep_convos']} deep / {metrics['moderate_convos']} mod / {metrics['shallow_convos']} shallow | "
                  f"{metrics['first_mention']} to {metrics['last_mention']}")

    # Step 2: Run each model
    # Structure: results[model_name][topic_name] = {"blind": score, "informed": score, ...}
    all_results = {}

    for model in MODELS:
        print(f"\n{'=' * 70}")
        print(f"MODEL: {model}")
        print(f"{'=' * 70}")

        # Warm up model (first call loads it into VRAM)
        print(f"  Loading {model} into GPU...")
        ask_model(model, "Say OK.")
        print(f"  Ready.\n")

        all_results[model] = {}

        for topic in TOPICS:
            fact = topic["fact"]
            metrics = topic_metrics[topic["name"]]

            print(f"  {topic['name']}:")

            # Informed test only (we already have blind data from qwen2.5)
            prompt = build_informed_prompt(fact, metrics)
            response, elapsed = ask_model(model, prompt)
            score = extract_score(response)

            # Also get reasoning
            reasoning = ""
            try:
                text = strip_thinking(response)
                if "```" in text:
                    text = text.split("```")[1].replace("json", "").strip()
                reasoning = json.loads(text).get("reasoning", "")
            except (json.JSONDecodeError, ValueError, KeyError):
                reasoning = strip_thinking(response)[:100]

            print(f"    Score: {score}/10 ({elapsed:.1f}s)")
            print(f"    Why: {reasoning}")

            all_results[model][topic["name"]] = {
                "score": score,
                "time": elapsed,
                "reasoning": reasoning,
                "raw": response,
            }

    # Step 3: Comparison table
    print(f"\n{'=' * 70}")
    print("COMPARISON: Informed Significance Scores Across Models")
    print(f"{'=' * 70}")

    # Header
    header = f"{'Topic':<20} {'Convos':>6}"
    for model in MODELS:
        short_name = model.split(":")[0]
        header += f" {short_name:>12}"
    print(header)
    print(f"{'─' * 20} {'─' * 6}" + "".join([f" {'─' * 12}"] * len(MODELS)))

    for topic in TOPICS:
        name = topic["name"]
        convos = topic_metrics[name]["recurrence"]
        row = f"{name:<20} {convos:>6}"
        for model in MODELS:
            score = all_results[model][name]["score"]
            row += f" {str(score):>12}"
        print(row)

    # Prior baseline results can be added here for comparison after running
    # the scoring pipeline on your own data.


if __name__ == "__main__":
    main()
