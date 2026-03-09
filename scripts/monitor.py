"""
Live progress monitor for fact extraction.
Run: python scripts/monitor.py
"""

import contextlib
import sqlite3
import time
import sys

from config import DATABASE_FILE

# Total conversations with 6+ messages
TOTAL_TARGET = None  # Dynamically determined from DB if not set

def get_stats():
    global TOTAL_TARGET
    with contextlib.closing(sqlite3.connect(DATABASE_FILE)) as conn:
        done = conn.execute("SELECT COUNT(*) FROM extraction_log").fetchone()[0]
        facts = conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()[0]
        active = conn.execute("SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL").fetchone()[0]
        remaining = conn.execute("""
            SELECT COUNT(*) FROM conversations c
            LEFT JOIN extraction_log e ON c.id = e.conversation_id
            WHERE e.conversation_id IS NULL AND c.message_count >= 6
        """).fetchone()[0]
        if TOTAL_TARGET is None:
            TOTAL_TARGET = done + remaining
    return done, facts, active, remaining

def progress_bar(pct, width=40):
    filled = int(width * pct / 100)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}]"

def main():
    print("\n" + "=" * 60)
    print("  FACT EXTRACTION PROGRESS MONITOR")
    print("=" * 60)
    print("  Press Ctrl+C to exit\n")

    start_done, _, _, start_remaining = get_stats()
    start_time = time.time()
    total = start_done + start_remaining

    last_done = start_done

    try:
        while True:
            done, facts, active, remaining = get_stats()

            # Calculate progress
            pct = (done / total * 100) if total > 0 else 0

            # Calculate rate
            elapsed = time.time() - start_time
            processed = done - start_done
            rate = processed / (elapsed / 60) if elapsed > 60 else 0

            # ETA
            if rate > 0:
                eta_min = remaining / rate
                eta_str = f"{eta_min:.0f}m" if eta_min < 60 else f"{eta_min/60:.1f}h"
            else:
                eta_str = "calculating..."

            # Build display
            bar = progress_bar(pct)

            # Clear line and print
            sys.stdout.write("\r" + " " * 80 + "\r")
            sys.stdout.write(f"  {bar} {pct:5.1f}%\n")
            sys.stdout.write(f"  Conversations: {done}/{total} | Remaining: {remaining}\n")
            sys.stdout.write(f"  Facts: {facts} ({active} active)\n")
            sys.stdout.write(f"  Rate: {rate:.1f}/min | ETA: {eta_str}\n")
            sys.stdout.write("\033[4A")  # Move cursor up 4 lines
            sys.stdout.flush()

            if remaining == 0:
                sys.stdout.write("\n\n\n\n")
                print("\n  ✓ EXTRACTION COMPLETE!")
                print(f"  Total facts: {facts} ({active} active)")
                break

            time.sleep(5)

    except KeyboardInterrupt:
        sys.stdout.write("\n\n\n\n")
        print("\n  Monitoring stopped. Extraction continues in background.")

if __name__ == "__main__":
    main()
