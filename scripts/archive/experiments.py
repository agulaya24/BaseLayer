"""
Phase 1 Experiments — SQLite Ground Truth
Run: python experiments.py
"""

import contextlib
import sqlite3
from pathlib import Path
from collections import Counter
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
DB = PROJECT_ROOT / "data" / "database" / "memory.db"


def experiment_1_topic_clusters():
    """Find your most common conversation topics by title keywords."""
    print("\n" + "="*60)
    print("EXPERIMENT 1: Topic Clusters (by title keywords)")
    print("="*60)

    with contextlib.closing(sqlite3.connect(DB)) as conn:
        cursor = conn.execute("SELECT title FROM conversations WHERE title IS NOT NULL")

        # Extract words from titles
        words = []
        for (title,) in cursor:
            words.extend(title.lower().split())

        # Filter noise words and count
        noise = {'the', 'a', 'an', 'and', 'or', 'for', 'to', 'in', 'on', 'with', 'of', 'is', 'it'}
        word_counts = Counter(w for w in words if len(w) > 2 and w not in noise)

        print("\nTop 20 topic keywords:")
        for word, count in word_counts.most_common(20):
            print(f"  {word}: {count}")


def experiment_2_conversation_depth():
    """Analyze which conversations went deepest (most back-and-forth)."""
    print("\n" + "="*60)
    print("EXPERIMENT 2: Deepest Conversations")
    print("="*60)

    with contextlib.closing(sqlite3.connect(DB)) as conn:
        cursor = conn.execute("""
            SELECT c.title, c.message_count, c.created_at
            FROM conversations c
            WHERE c.message_count > 30
            ORDER BY c.message_count DESC
            LIMIT 15
        """)

        print("\nConversations with 30+ messages:")
        for title, count, created in cursor:
            date = datetime.fromtimestamp(created).strftime("%Y-%m-%d") if created else "?"
            print(f"  [{count:3d} msgs] [{date}] {title[:50]}")


def experiment_3_your_questions():
    """Find questions you've asked repeatedly (patterns in your thinking)."""
    print("\n" + "="*60)
    print("EXPERIMENT 3: Your Repeated Questions")
    print("="*60)

    with contextlib.closing(sqlite3.connect(DB)) as conn:
        cursor = conn.execute("""
            SELECT content_text FROM messages
            WHERE role = 'user' AND content_text LIKE '%?%'
        """)

        # Extract question patterns
        question_starts = Counter()
        for (text,) in cursor:
            lines = text.split('\n')
            for line in lines:
                if '?' in line:
                    # Get first few words of questions
                    words = line.strip().split()[:4]
                    if len(words) >= 2:
                        pattern = ' '.join(words).lower()
                        question_starts[pattern] += 1

        print("\nYour most common question patterns:")
        for pattern, count in question_starts.most_common(15):
            if count > 2:
                print(f"  ({count}x) {pattern}...")


def experiment_4_time_patterns():
    """When do you have conversations? Time-of-day and day patterns."""
    print("\n" + "="*60)
    print("EXPERIMENT 4: Conversation Time Patterns")
    print("="*60)

    with contextlib.closing(sqlite3.connect(DB)) as conn:
        cursor = conn.execute("""
            SELECT created_at FROM conversations WHERE created_at IS NOT NULL
        """)

        hours = Counter()
        weekdays = Counter()
        months = Counter()

        for (ts,) in cursor:
            dt = datetime.fromtimestamp(ts)
            hours[dt.hour] += 1
            weekdays[dt.strftime("%A")] += 1
            months[dt.strftime("%Y-%m")] += 1

        print("\nConversations by hour of day:")
        for hour in sorted(hours.keys()):
            bar = "#" * (hours[hour] // 5)
            print(f"  {hour:02d}:00  {bar} ({hours[hour]})")

        print("\nConversations by day of week:")
        for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]:
            print(f"  {day:10s}: {weekdays.get(day, 0)}")

        print("\nMost active months:")
        for month, count in months.most_common(6):
            print(f"  {month}: {count}")


def experiment_5_search_your_ideas():
    """Search for specific topics you've discussed."""
    print("\n" + "="*60)
    print("EXPERIMENT 5: Search Your Ideas")
    print("="*60)

    with contextlib.closing(sqlite3.connect(DB)) as conn:
        # Search terms relevant to your memory project
        terms = ["retrieval", "context window", "vector", "embedding", "persistent", "local storage"]

        for term in terms:
            cursor = conn.execute("""
                SELECT COUNT(DISTINCT conversation_id)
                FROM messages
                WHERE content_text LIKE ?
            """, (f"%{term}%",))
            count = cursor.fetchone()[0]
            if count > 0:
                print(f"  '{term}': mentioned in {count} conversations")


def experiment_6_assistant_patterns():
    """What does the assistant talk about most? (Topics in responses)"""
    print("\n" + "="*60)
    print("EXPERIMENT 6: What ChatGPT Talked About")
    print("="*60)

    with contextlib.closing(sqlite3.connect(DB)) as conn:
        cursor = conn.execute("""
            SELECT content_text FROM messages
            WHERE role = 'assistant' AND length(content_text) > 100
            LIMIT 1000
        """)

        # Sample vocabulary from assistant responses
        words = []
        for (text,) in cursor:
            words.extend(text.lower().split())

        # Filter to meaningful words
        noise = {'the', 'a', 'an', 'and', 'or', 'for', 'to', 'in', 'on', 'with', 'of',
                 'is', 'it', 'this', 'that', 'be', 'as', 'are', 'was', 'were', 'been',
                 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
                 'should', 'may', 'might', 'can', 'if', 'you', 'your', 'i', 'we', 'they',
                 'but', 'not', 'so', 'at', 'by', 'from', 'about', 'into', 'which', 'their',
                 'also', 'more', 'some', 'any', 'these', 'those', 'each', 'all', 'both',
                 'such', 'than', 'then', 'when', 'where', 'how', 'what', 'who', 'why'}

        word_counts = Counter(w for w in words if len(w) > 3 and w not in noise and w.isalpha())

        print("\nMost frequent substantive words in assistant responses:")
        for word, count in word_counts.most_common(20):
            print(f"  {word}: {count}")


if __name__ == "__main__":
    print("="*60)
    print("PHASE 1 EXPERIMENTS — Ground Truth Analysis")
    print("="*60)

    experiment_1_topic_clusters()
    experiment_2_conversation_depth()
    experiment_3_your_questions()
    experiment_4_time_patterns()
    experiment_5_search_your_ideas()
    experiment_6_assistant_patterns()

    print("\n" + "="*60)
    print("DONE — These experiments use only SQLite queries")
    print("="*60)
