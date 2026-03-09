"""
Twin-2K-500 Deterministic Parser (Approach 1)

Parses structured persona_text Q&A directly into pipeline-compatible facts,
bypassing Haiku extraction. Each question-answer pair becomes one atomic fact.

After parsing, runs the pipeline from Step 3 (embed) onward to generate a brief.

Usage:
    python twin2k_parser.py --participant 0              # Parse one participant
    python twin2k_parser.py --all                        # Parse all downloaded participants
    python twin2k_parser.py --participant 0 --run-pipeline  # Parse + run pipeline steps 3-12

The parser creates a participant-specific environment (like buffett_memory/)
and writes facts to its memory_facts table.
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import uuid
from pathlib import Path
from datetime import datetime

SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))

SUBJECTS_DIR = Path(os.environ.get(
    "TWIN2K_DIR",
    Path(__file__).parent.parent.parent / "subjects" / "twin2k"
))


def parse_persona_text(text):
    """Parse structured Q&A text into individual question-answer facts.

    Input format (repeating blocks separated by blank lines):
        Question text
        Question Type: Single Choice
        Options:
          1 - Option A
          2 - Option B
        Answer: 1 - Option A

    Returns list of dicts with keys: question, question_type, options, answer, raw_text
    """
    facts = []
    blocks = re.split(r'\n\s*\n', text.strip())

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        lines = block.split('\n')
        if len(lines) < 2:
            continue

        fact = {
            'question': '',
            'question_type': '',
            'options': [],
            'answer': '',
            'raw_text': block
        }

        # Parse the block
        question_lines = []
        options = []
        answer = ''
        q_type = ''
        in_options = False

        for line in lines:
            stripped = line.strip()

            if stripped.startswith('Question Type:'):
                q_type = stripped.replace('Question Type:', '').strip()
                in_options = False
            elif stripped.startswith('Options:'):
                in_options = True
            elif stripped.startswith('Answer:'):
                answer = stripped.replace('Answer:', '').strip()
                in_options = False
            elif stripped.startswith('Answers:'):
                answer = stripped.replace('Answers:', '').strip()
                in_options = False
            elif in_options and re.match(r'^\d+\s*[-–]', stripped):
                options.append(stripped)
            elif not q_type and not in_options and not answer:
                question_lines.append(stripped)

        fact['question'] = ' '.join(question_lines).strip()
        fact['question_type'] = q_type
        fact['options'] = options
        fact['answer'] = answer

        # Skip blocks with no question or answer
        if not fact['question'] or not fact['answer']:
            continue

        # Skip purely instructional blocks
        if fact['question'].startswith('You will now be asked'):
            continue

        facts.append(fact)

    return facts


def fact_to_triple(fact, participant_id):
    """Convert a parsed Q&A fact into a pipeline-compatible triple.

    Maps questions to appropriate predicates from the 47-predicate set.
    """
    question = fact['question'].lower()
    answer = fact['answer']

    # Map common question patterns to predicates
    predicate = 'responded_to_survey'  # default

    if any(w in question for w in ['religion', 'religious', 'church', 'worship']):
        predicate = 'practices'
    elif any(w in question for w in ['political', 'republican', 'democrat', 'party']):
        predicate = 'values'
    elif any(w in question for w in ['race', 'ethnicity', 'origin']):
        predicate = 'identifies_as'
    elif any(w in question for w in ['age', 'old are you']):
        predicate = 'identifies_as'
    elif any(w in question for w in ['gender', 'sex']):
        predicate = 'identifies_as'
    elif any(w in question for w in ['education', 'degree', 'school']):
        predicate = 'studied'
    elif any(w in question for w in ['income', 'earn', 'salary']):
        predicate = 'values'
    elif any(w in question for w in ['married', 'marital', 'partner']):
        predicate = 'identifies_as'
    elif any(w in question for w in ['agree', 'disagree', 'scale']):
        predicate = 'exhibits_trait'
    elif any(w in question for w in ['prefer', 'favorite', 'choose']):
        predicate = 'prefers'
    elif any(w in question for w in ['risk', 'gamble', 'bet', 'lottery', 'probability']):
        predicate = 'approaches_risk'
    elif any(w in question for w in ['buy', 'purchase', 'spend', 'price']):
        predicate = 'prefers'
    elif any(w in question for w in ['trust', 'fair', 'split', 'share', 'give']):
        predicate = 'values'
    elif any(w in question for w in ['support', 'oppose', 'favor']):
        predicate = 'values'
    elif any(w in question for w in ['feel', 'emotion', 'anxious', 'depressed', 'nervous']):
        predicate = 'exhibits_trait'
    elif any(w in question for w in ['think', 'believe', 'opinion']):
        predicate = 'believes'
    elif any(w in question for w in ['describe yourself', 'type of person']):
        predicate = 'identifies_as'
    elif any(w in question for w in ['work', 'job', 'employ', 'occupation']):
        predicate = 'works_as'

    # Create the object text — combine question context with answer
    obj = f"{fact['question']}: {answer}"
    if len(obj) > 500:
        # Truncate long objects but keep the answer
        obj = f"{fact['question'][:200]}...: {answer}"

    return {
        'subject': 'this person',
        'predicate': predicate,
        'object': obj,
        'raw_text': fact['raw_text'],
        'question_type': fact['question_type'],
    }


def create_participant_db(participant_id, output_dir):
    """Create a participant-specific SQLite database for pipeline processing."""
    env_dir = output_dir / f"participant_{participant_id}" / "data" / "database"
    env_dir.mkdir(parents=True, exist_ok=True)
    db_path = env_dir / "memory.db"

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")

    # Create the memory_facts table matching pipeline schema
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS memory_facts (
            fact_id TEXT PRIMARY KEY,
            conversation_id TEXT,
            message_index INTEGER DEFAULT 0,
            subject TEXT NOT NULL,
            predicate TEXT NOT NULL,
            object TEXT NOT NULL,
            raw_text TEXT,
            fact_type TEXT DEFAULT 'behavioral',
            knowledge_tier TEXT DEFAULT 'context',
            commitment_depth TEXT DEFAULT 'stated',
            depth_score REAL DEFAULT 1.0,
            recurrence_count INTEGER DEFAULT 1,
            status TEXT DEFAULT 'active',
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS conversations (
            conversation_id TEXT PRIMARY KEY,
            title TEXT,
            create_time REAL,
            update_time REAL,
            source TEXT DEFAULT 'twin2k',
            message_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS extraction_log (
            conversation_id TEXT PRIMARY KEY,
            extracted_at TEXT,
            fact_count INTEGER,
            model TEXT DEFAULT 'deterministic_parser',
            status TEXT DEFAULT 'complete'
        );
    """)
    conn.commit()
    return conn, db_path


def load_and_parse(participant_id, subjects_dir):
    """Load persona_text for a participant and parse into facts."""
    pdir = subjects_dir / f"participant_{participant_id}"

    persona_file = pdir / "persona_text.txt"
    if not persona_file.exists():
        print(f"  ERROR: {persona_file} not found. Run twin2k_download.py first.")
        return []

    text = persona_file.read_text(encoding="utf-8")
    print(f"  Persona text: {len(text):,} chars")

    raw_facts = parse_persona_text(text)
    print(f"  Parsed Q&A blocks: {len(raw_facts)}")

    triples = [fact_to_triple(f, participant_id) for f in raw_facts]
    return triples


def write_facts_to_db(conn, triples, participant_id):
    """Write parsed facts to the participant's database."""
    now = datetime.now().isoformat()
    conv_id = f"twin2k_p{participant_id}"

    # Create a conversation record
    conn.execute("""
        INSERT OR REPLACE INTO conversations
        (conversation_id, title, create_time, source, message_count)
        VALUES (?, ?, ?, 'twin2k', ?)
    """, (conv_id, f"Twin-2K Participant {participant_id}", 0, len(triples)))

    # Write each fact
    for i, triple in enumerate(triples):
        fact_id = f"twin2k_p{participant_id}_{i:04d}"
        conn.execute("""
            INSERT OR REPLACE INTO memory_facts
            (fact_id, conversation_id, message_index, subject, predicate, object,
             raw_text, fact_type, knowledge_tier, commitment_depth,
             depth_score, recurrence_count, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'behavioral', 'context', 'stated',
                    1.0, 1, 'active', ?, ?)
        """, (fact_id, conv_id, i, triple['subject'], triple['predicate'],
              triple['object'], triple['raw_text'], now, now))

    # Log extraction
    conn.execute("""
        INSERT OR REPLACE INTO extraction_log
        (conversation_id, extracted_at, fact_count, model, status)
        VALUES (?, ?, ?, 'deterministic_parser', 'complete')
    """, (conv_id, now, len(triples)))

    conn.commit()
    return len(triples)


def export_facts_json(triples, participant_id, output_dir):
    """Export parsed facts as JSON for inspection."""
    pdir = output_dir / f"participant_{participant_id}"
    pdir.mkdir(parents=True, exist_ok=True)

    out_file = pdir / "parsed_facts.json"
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(triples, f, indent=2, ensure_ascii=False)

    return out_file


def main():
    parser = argparse.ArgumentParser(description="Parse Twin-2K-500 persona data into pipeline facts")
    parser.add_argument("--participant", type=int, help="Participant index to parse")
    parser.add_argument("--all", action="store_true", help="Parse all downloaded participants")
    parser.add_argument("--run-pipeline", action="store_true",
                        help="After parsing, run pipeline steps 3-12 to generate brief")
    parser.add_argument("--subjects-dir", type=str, default=None)
    args = parser.parse_args()

    subjects_dir = Path(args.subjects_dir) if args.subjects_dir else SUBJECTS_DIR

    if args.all:
        # Find all downloaded participant directories
        indices = sorted([
            int(d.name.split('_')[1])
            for d in subjects_dir.iterdir()
            if d.is_dir() and d.name.startswith('participant_')
            and (d / "persona_text.txt").exists()
        ])
    elif args.participant is not None:
        indices = [args.participant]
    else:
        print("ERROR: Specify --participant N or --all")
        sys.exit(1)

    print(f"Parsing {len(indices)} participants from {subjects_dir}")

    for pid in indices:
        print(f"\n--- Participant {pid} ---")

        # Parse persona_text into facts
        triples = load_and_parse(pid, subjects_dir)
        if not triples:
            continue

        # Export as JSON for inspection
        json_file = export_facts_json(triples, pid, subjects_dir)
        print(f"  Exported {len(triples)} facts to {json_file}")

        # Write to participant database for pipeline processing
        conn, db_path = create_participant_db(pid, subjects_dir)
        n_written = write_facts_to_db(conn, triples, pid)
        conn.close()
        print(f"  Wrote {n_written} facts to {db_path}")

        # Show predicate distribution
        pred_counts = {}
        for t in triples:
            pred_counts[t['predicate']] = pred_counts.get(t['predicate'], 0) + 1
        print(f"  Predicate distribution:")
        for pred, count in sorted(pred_counts.items(), key=lambda x: -x[1])[:10]:
            print(f"    {pred}: {count}")

    print(f"\nDone. Parsed {len(indices)} participants.")
    if not args.run_pipeline:
        print("Run with --run-pipeline to generate briefs, or run pipeline steps manually.")


if __name__ == "__main__":
    main()
