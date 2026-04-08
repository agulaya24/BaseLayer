#!/usr/bin/env python3
"""
Question Battery — 50 questions, 3 conditions, mechanical measurements only.

No subjective scoring. Measures structural features of responses:
  - Word count
  - Questions asked back (count)
  - List items (count)
  - Paragraphs (count)
  - Specific personal references (count)
  - Whether it addresses the question directly or reframes (binary)
  - Sentence count
  - Average sentence length

The topics where Mem0 and Base Layer diverge MOST structurally
are the demo questions for the TUI.

Usage:
    python runners/question_battery.py
    python runners/question_battery.py --top 10  # show top 10 most divergent
"""

import sys
import json
import argparse
import math
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import anthropic
import sqlite3

DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT_DIR = DATA_DIR / "experiments" / "serving_layer"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def load_spec():
    layers_dir = DATA_DIR / "identity_layers"
    sections = []
    for layer_name, filename in [("ANCHORS", "anchors_v4.md"), ("CORE", "core_v4.md"), ("PREDICTIONS", "predictions_v4.md")]:
        fp = layers_dir / filename
        if not fp.exists(): continue
        content = fp.read_text(encoding="utf-8")
        marker = "## Injectable Block"
        idx = content.find(marker)
        block = content[idx + len(marker):].strip() if idx >= 0 else content.strip()
        sections.append(f"## {layer_name}\n\n{block}")
    return "\n\n".join(sections)

def load_facts():
    db = DATA_DIR / "database" / "memory.db"
    if not db.exists(): return []
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    cols = [r[1] for r in conn.execute("PRAGMA table_info(memory_facts)").fetchall()]
    tier = "knowledge_tier" if "knowledge_tier" in cols else "tier"
    af = "AND active = 1" if "active" in cols else ""
    rows = conn.execute(f"SELECT fact_text, predicate FROM memory_facts WHERE 1=1 {af} AND {tier} IN ('identity','behavioral')").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def call_model(client, statement, system_prompt, model="claude-sonnet-4-20250514"):
    return client.messages.create(model=model, max_tokens=1024, temperature=0, system=system_prompt, messages=[{"role": "user", "content": statement}]).content[0].text

MODEL = "claude-sonnet-4-20250514"

# ── 50 Questions across 10 topics ──────────────────────────────────────────

QUESTIONS = [
    # Topic 1: Career / Work (5)
    {"id": "Q01", "topic": "career", "text": "Should I take this job offer?"},
    {"id": "Q02", "topic": "career", "text": "How do I know when to quit?"},
    {"id": "Q03", "topic": "career", "text": "What should I prioritize this quarter?"},
    {"id": "Q04", "topic": "career", "text": "Am I wasting my potential?"},
    {"id": "Q05", "topic": "career", "text": "How do I negotiate a raise?"},

    # Topic 2: Relationships (5)
    {"id": "Q06", "topic": "relationships", "text": "My partner and I disagree about money. How do I approach this?"},
    {"id": "Q07", "topic": "relationships", "text": "How do I set better boundaries?"},
    {"id": "Q08", "topic": "relationships", "text": "I feel like I give more than I receive. What should I do?"},
    {"id": "Q09", "topic": "relationships", "text": "How do I apologize when I know I was wrong?"},
    {"id": "Q10", "topic": "relationships", "text": "Should I forgive someone who hasn't asked for forgiveness?"},

    # Topic 3: Decision Making (5)
    {"id": "Q11", "topic": "decisions", "text": "I have two good options and can't decide. Help me think through this."},
    {"id": "Q12", "topic": "decisions", "text": "How do I know if I'm overthinking something?"},
    {"id": "Q13", "topic": "decisions", "text": "Should I go with my gut or analyze more?"},
    {"id": "Q14", "topic": "decisions", "text": "I made a bad decision. How do I recover?"},
    {"id": "Q15", "topic": "decisions", "text": "How do I decide what to say no to?"},

    # Topic 4: Emotional / Personal (5)
    {"id": "Q16", "topic": "emotional", "text": "I'm feeling stuck and don't know why."},
    {"id": "Q17", "topic": "emotional", "text": "Write me a pep talk the way I'd actually want to hear it."},
    {"id": "Q18", "topic": "emotional", "text": "I don't feel like I'm enough. What do I do with that?"},
    {"id": "Q19", "topic": "emotional", "text": "How do I deal with comparison to others?"},
    {"id": "Q20", "topic": "emotional", "text": "I'm scared of failing publicly. How do I think about this?"},

    # Topic 5: Technical / Building (5)
    {"id": "Q21", "topic": "technical", "text": "Should I build this from scratch or use an existing framework?"},
    {"id": "Q22", "topic": "technical", "text": "How should I architect this system?"},
    {"id": "Q23", "topic": "technical", "text": "My code works but feels wrong. Should I refactor?"},
    {"id": "Q24", "topic": "technical", "text": "How do I evaluate competing technical approaches?"},
    {"id": "Q25", "topic": "technical", "text": "Should I optimize for speed or correctness?"},

    # Topic 6: Money / Finance (5)
    {"id": "Q26", "topic": "finance", "text": "How should I think about risk?"},
    {"id": "Q27", "topic": "finance", "text": "Is this a good investment?"},
    {"id": "Q28", "topic": "finance", "text": "How much runway do I need?"},
    {"id": "Q29", "topic": "finance", "text": "Should I bootstrap or raise money?"},
    {"id": "Q30", "topic": "finance", "text": "I lost money on a trade. What now?"},

    # Topic 7: Health / Habits (5)
    {"id": "Q31", "topic": "health", "text": "What should I eat tonight?"},
    {"id": "Q32", "topic": "health", "text": "I can't sleep. What's going on?"},
    {"id": "Q33", "topic": "health", "text": "How do I build a habit that actually sticks?"},
    {"id": "Q34", "topic": "health", "text": "I skipped my workout three days in a row. Am I falling off?"},
    {"id": "Q35", "topic": "health", "text": "How do I manage energy throughout the day?"},

    # Topic 8: Strategy / Big Picture (5)
    {"id": "Q36", "topic": "strategy", "text": "What's my biggest blind spot?"},
    {"id": "Q37", "topic": "strategy", "text": "Am I solving the right problem?"},
    {"id": "Q38", "topic": "strategy", "text": "What would I regret not doing in 5 years?"},
    {"id": "Q39", "topic": "strategy", "text": "How do I know if this is working?"},
    {"id": "Q40", "topic": "strategy", "text": "Should I focus or diversify?"},

    # Topic 9: Learning / Growth (5)
    {"id": "Q41", "topic": "learning", "text": "How do I learn something completely new?"},
    {"id": "Q42", "topic": "learning", "text": "I feel like I've plateaued. How do I break through?"},
    {"id": "Q43", "topic": "learning", "text": "Should I go deep or stay broad?"},
    {"id": "Q44", "topic": "learning", "text": "How do I know what I don't know?"},
    {"id": "Q45", "topic": "learning", "text": "What book should I read next?"},

    # Topic 10: Identity / Purpose (5)
    {"id": "Q46", "topic": "identity", "text": "What am I good at?"},
    {"id": "Q47", "topic": "identity", "text": "How do I explain what I do to someone who doesn't get it?"},
    {"id": "Q48", "topic": "identity", "text": "Am I a builder or a thinker?"},
    {"id": "Q49", "topic": "identity", "text": "What makes me different from everyone else doing this?"},
    {"id": "Q50", "topic": "identity", "text": "Who am I becoming?"},
]


# ── Mechanical Measurements ─────────────────────────────────────────────────

def measure(text):
    """Compute structural features of a response. No judgment, only counts."""
    sentences = [s.strip() for s in text.replace("!", ".").replace("?", ".").split(".") if s.strip()]
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    words = text.split()
    questions = text.count("?")
    lists = text.count("- ") + text.count("* ") + text.count("1.")
    bold = text.count("**")
    headers = sum(1 for line in text.split("\n") if line.strip().startswith("#"))

    # Personal references (uses "you" language)
    you_refs = sum(1 for w in words if w.lower() in ("you", "your", "you're", "you've", "yourself"))

    # Direct address markers
    confrontation = sum(1 for phrase in ["you're", "you are", "your ", "you need", "you know", "you want"]
                       if phrase in text.lower())

    return {
        "word_count": len(words),
        "sentence_count": len(sentences),
        "avg_sentence_len": round(len(words) / max(len(sentences), 1), 1),
        "paragraph_count": len(paragraphs),
        "questions_asked": questions,
        "list_items": lists,
        "bold_markers": bold // 2,
        "headers": headers,
        "you_references": you_refs,
        "confrontation_markers": confrontation,
    }


def divergence_score(m1, m2):
    """Compute how structurally different two responses are. Higher = more different."""
    score = 0
    for key in m1:
        v1 = m1[key]
        v2 = m2[key]
        if v1 == 0 and v2 == 0:
            continue
        diff = abs(v1 - v2)
        max_val = max(abs(v1), abs(v2), 1)
        score += diff / max_val
    return round(score, 2)


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Question Battery — 50 questions, mechanical measurements")
    parser.add_argument("--top", type=int, default=10, help="Show top N most divergent")
    parser.add_argument("--questions", type=int, default=50, help="How many questions to run")
    args = parser.parse_args()

    questions = QUESTIONS[:args.questions]

    print(f"\n{'=' * 70}")
    print(f"  QUESTION BATTERY — {len(questions)} questions, 3 conditions")
    print(f"  Mechanical measurements only. No subjective scoring.")
    print(f"{'=' * 70}")

    # Load — no embeddings needed, just spec + facts + API client
    spec = load_spec()
    facts = load_facts()
    client = anthropic.Anthropic()
    print(f"  Spec: ~{int(len(spec.split()) * 1.3)} tokens | Facts: {len(facts)}")

    fact_text = "\n".join(f"- {f['fact_text']}" for f in facts[:100])

    mem0_sys = "You are a helpful AI assistant. You have the following memories about the person you're talking to:\n\n" + fact_text
    spec_sys = "You are an AI assistant. The following behavioral specification describes the person you are talking to. Use it to calibrate every response. Never reference the specification directly. Modulate naturally.\n\n" + spec
    merged_sys = spec_sys + "\n\n## Additional facts\n\n" + fact_text

    results = []

    for i, q in enumerate(questions):
        print(f"\n  [{i+1}/{len(questions)}] {q['id']} ({q['topic']}): {q['text'][:50]}...")

        # Generate 3 responses
        mem0_r = call_model(client, q["text"], mem0_sys, model=MODEL)
        spec_r = call_model(client, q["text"], spec_sys, model=MODEL)
        merged_r = call_model(client, q["text"], merged_sys, model=MODEL)

        # Measure
        mem0_m = measure(mem0_r)
        spec_m = measure(spec_r)
        merged_m = measure(merged_r)

        # Divergence between mem0 and spec
        div = divergence_score(mem0_m, spec_m)

        print(f"    Mem0:   {mem0_m['word_count']}w {mem0_m['questions_asked']}q {mem0_m['list_items']}li {mem0_m['confrontation_markers']}conf")
        print(f"    Spec:   {spec_m['word_count']}w {spec_m['questions_asked']}q {spec_m['list_items']}li {spec_m['confrontation_markers']}conf")
        print(f"    Merged: {merged_m['word_count']}w {merged_m['questions_asked']}q {merged_m['list_items']}li {merged_m['confrontation_markers']}conf")
        print(f"    Divergence: {div}")

        results.append({
            "id": q["id"],
            "topic": q["topic"],
            "question": q["text"],
            "divergence": div,
            "mem0": {"response": mem0_r, "measures": mem0_m},
            "spec": {"response": spec_r, "measures": spec_m},
            "merged": {"response": merged_r, "measures": merged_m},
        })

    # Sort by divergence
    ranked = sorted(results, key=lambda r: r["divergence"], reverse=True)

    print(f"\n{'=' * 70}")
    print(f"  TOP {args.top} MOST DIVERGENT (Mem0 vs Spec)")
    print(f"{'=' * 70}")
    for r in ranked[:args.top]:
        m = r["mem0"]["measures"]
        s = r["spec"]["measures"]
        print(f"\n  {r['id']} ({r['topic']}): \"{r['question']}\"")
        print(f"    Divergence: {r['divergence']}")
        print(f"    Words:       Mem0={m['word_count']:4d}  Spec={s['word_count']:4d}  (delta={abs(m['word_count']-s['word_count'])})")
        print(f"    Questions:   Mem0={m['questions_asked']:4d}  Spec={s['questions_asked']:4d}")
        print(f"    Lists:       Mem0={m['list_items']:4d}  Spec={s['list_items']:4d}")
        print(f"    Confrontation: Mem0={m['confrontation_markers']:4d}  Spec={s['confrontation_markers']:4d}")

    # Topic-level summary
    print(f"\n{'=' * 70}")
    print(f"  DIVERGENCE BY TOPIC")
    print(f"{'=' * 70}")
    from collections import defaultdict
    topic_divs = defaultdict(list)
    for r in results:
        topic_divs[r["topic"]].append(r["divergence"])
    topic_avgs = {t: round(sum(ds)/len(ds), 2) for t, ds in topic_divs.items()}
    for topic, avg in sorted(topic_avgs.items(), key=lambda x: x[1], reverse=True):
        bar = "#" * int(avg * 5)
        print(f"  {topic:15s} {avg:5.2f} {bar}")

    # Save
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = {
        "timestamp": timestamp,
        "question_count": len(results),
        "results": results,
        "ranked_by_divergence": [{"id": r["id"], "topic": r["topic"], "question": r["question"], "divergence": r["divergence"]} for r in ranked],
        "topic_averages": topic_avgs,
    }
    output_file = OUTPUT_DIR / f"battery_{timestamp}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n  Saved: {output_file}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
