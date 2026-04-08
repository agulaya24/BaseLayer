#!/usr/bin/env python3
"""
Question Battery — Multi-subject version. Same 50 questions, different subject's spec and facts.

Usage:
    python runners/question_battery_subject.py --subject buffett
    python runners/question_battery_subject.py --subject marks
"""

import sys
import json
import argparse
import sqlite3
from pathlib import Path
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import anthropic

SUBJECTS_DIR = Path(__file__).parent.parent.parent / "subjects"
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "experiments" / "serving_layer"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_spec(subject):
    layers_dir = SUBJECTS_DIR / f"{subject}_memory" / "data" / "identity_layers"
    sections = []
    for layer_name, filename in [("ANCHORS", "anchors_v4.md"), ("CORE", "core_v4.md"), ("PREDICTIONS", "predictions_v4.md")]:
        fp = layers_dir / filename
        if not fp.exists():
            continue
        content = fp.read_text(encoding="utf-8")
        marker = "## Injectable Block"
        idx = content.find(marker)
        block = content[idx + len(marker):].strip() if idx >= 0 else content.strip()
        sections.append(f"## {layer_name}\n\n{block}")
    return "\n\n".join(sections)


def load_facts(subject):
    db = SUBJECTS_DIR / f"{subject}_memory" / "data" / "database" / "memory.db"
    if not db.exists():
        return []
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    cols = [r[1] for r in conn.execute("PRAGMA table_info(memory_facts)").fetchall()]
    tier = "knowledge_tier" if "knowledge_tier" in cols else "tier"
    af = "AND active = 1" if "active" in cols else ""
    rows = conn.execute(f"SELECT fact_text, predicate FROM memory_facts WHERE 1=1 {af} AND {tier} IN ('identity','behavioral')").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def call_model(client, statement, system_prompt):
    return client.messages.create(
        model="claude-sonnet-4-20250514", max_tokens=1024, temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": statement}],
    ).content[0].text


def measure(text):
    sentences = [s.strip() for s in text.replace("!", ".").replace("?", ".").split(".") if s.strip()]
    words = text.split()
    return {
        "word_count": len(words),
        "sentence_count": len(sentences),
        "avg_sentence_len": round(len(words) / max(len(sentences), 1), 1),
        "paragraph_count": len([p for p in text.split("\n\n") if p.strip()]),
        "questions_asked": text.count("?"),
        "list_items": text.count("- ") + text.count("* ") + text.count("1."),
        "bold_markers": text.count("**") // 2,
        "headers": sum(1 for line in text.split("\n") if line.strip().startswith("#")),
        "you_references": sum(1 for w in words if w.lower() in ("you", "your", "you're", "you've", "yourself")),
        "confrontation_markers": sum(1 for p in ["you're", "you are", "your ", "you need", "you know", "you want"] if p in text.lower()),
    }


def divergence_score(m1, m2):
    score = 0
    for key in m1:
        v1, v2 = m1[key], m2[key]
        if v1 == 0 and v2 == 0:
            continue
        score += abs(v1 - v2) / max(abs(v1), abs(v2), 1)
    return round(score, 2)


QUESTIONS = [
    {"id": "Q01", "topic": "career", "text": "Should I take this job offer?"},
    {"id": "Q02", "topic": "career", "text": "How do I know when to quit?"},
    {"id": "Q03", "topic": "career", "text": "What should I prioritize this quarter?"},
    {"id": "Q04", "topic": "career", "text": "Am I wasting my potential?"},
    {"id": "Q05", "topic": "career", "text": "How do I negotiate a raise?"},
    {"id": "Q06", "topic": "relationships", "text": "My partner and I disagree about money. How do I approach this?"},
    {"id": "Q07", "topic": "relationships", "text": "How do I set better boundaries?"},
    {"id": "Q08", "topic": "relationships", "text": "I feel like I give more than I receive. What should I do?"},
    {"id": "Q09", "topic": "relationships", "text": "How do I apologize when I know I was wrong?"},
    {"id": "Q10", "topic": "relationships", "text": "Should I forgive someone who hasn't asked for forgiveness?"},
    {"id": "Q11", "topic": "decisions", "text": "I have two good options and can't decide. Help me think through this."},
    {"id": "Q12", "topic": "decisions", "text": "How do I know if I'm overthinking something?"},
    {"id": "Q13", "topic": "decisions", "text": "Should I go with my gut or analyze more?"},
    {"id": "Q14", "topic": "decisions", "text": "I made a bad decision. How do I recover?"},
    {"id": "Q15", "topic": "decisions", "text": "How do I decide what to say no to?"},
    {"id": "Q16", "topic": "emotional", "text": "I'm feeling stuck and don't know why."},
    {"id": "Q17", "topic": "emotional", "text": "Write me a pep talk the way I'd actually want to hear it."},
    {"id": "Q18", "topic": "emotional", "text": "I don't feel like I'm enough. What do I do with that?"},
    {"id": "Q19", "topic": "emotional", "text": "How do I deal with comparison to others?"},
    {"id": "Q20", "topic": "emotional", "text": "I'm scared of failing publicly. How do I think about this?"},
    {"id": "Q21", "topic": "technical", "text": "Should I build this from scratch or use an existing framework?"},
    {"id": "Q22", "topic": "technical", "text": "How should I architect this system?"},
    {"id": "Q23", "topic": "technical", "text": "My code works but feels wrong. Should I refactor?"},
    {"id": "Q24", "topic": "technical", "text": "How do I evaluate competing technical approaches?"},
    {"id": "Q25", "topic": "technical", "text": "Should I optimize for speed or correctness?"},
    {"id": "Q26", "topic": "finance", "text": "How should I think about risk?"},
    {"id": "Q27", "topic": "finance", "text": "Is this a good investment?"},
    {"id": "Q28", "topic": "finance", "text": "How much runway do I need?"},
    {"id": "Q29", "topic": "finance", "text": "Should I bootstrap or raise money?"},
    {"id": "Q30", "topic": "finance", "text": "I lost money on a trade. What now?"},
    {"id": "Q31", "topic": "health", "text": "What should I eat tonight?"},
    {"id": "Q32", "topic": "health", "text": "I can't sleep. What's going on?"},
    {"id": "Q33", "topic": "health", "text": "How do I build a habit that actually sticks?"},
    {"id": "Q34", "topic": "health", "text": "I skipped my workout three days in a row. Am I falling off?"},
    {"id": "Q35", "topic": "health", "text": "How do I manage energy throughout the day?"},
    {"id": "Q36", "topic": "strategy", "text": "What's my biggest blind spot?"},
    {"id": "Q37", "topic": "strategy", "text": "Am I solving the right problem?"},
    {"id": "Q38", "topic": "strategy", "text": "What would I regret not doing in 5 years?"},
    {"id": "Q39", "topic": "strategy", "text": "How do I know if this is working?"},
    {"id": "Q40", "topic": "strategy", "text": "Should I focus or diversify?"},
    {"id": "Q41", "topic": "learning", "text": "How do I learn something completely new?"},
    {"id": "Q42", "topic": "learning", "text": "I feel like I've plateaued. How do I break through?"},
    {"id": "Q43", "topic": "learning", "text": "Should I go deep or stay broad?"},
    {"id": "Q44", "topic": "learning", "text": "How do I know what I don't know?"},
    {"id": "Q45", "topic": "learning", "text": "What book should I read next?"},
    {"id": "Q46", "topic": "identity", "text": "What am I good at?"},
    {"id": "Q47", "topic": "identity", "text": "How do I explain what I do to someone who doesn't get it?"},
    {"id": "Q48", "topic": "identity", "text": "Am I a builder or a thinker?"},
    {"id": "Q49", "topic": "identity", "text": "What makes me different from everyone else doing this?"},
    {"id": "Q50", "topic": "identity", "text": "Who am I becoming?"},
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", required=True)
    parser.add_argument("--questions", type=int, default=50)
    args = parser.parse_args()

    questions = QUESTIONS[:args.questions]
    subject = args.subject

    print(f"\n{'='*70}")
    print(f"  QUESTION BATTERY — {subject} — {len(questions)} questions")
    print(f"{'='*70}")

    spec = load_spec(subject)
    facts = load_facts(subject)
    client = anthropic.Anthropic()
    print(f"  Spec: ~{int(len(spec.split())*1.3)} tokens | Facts: {len(facts)}")

    fact_text = "\n".join(f"- {f['fact_text']}" for f in facts[:100])
    mem0_sys = "You are a helpful AI assistant. You have the following memories about the person you're talking to:\n\n" + fact_text
    spec_sys = "You are an AI assistant. The following behavioral specification describes the person you are talking to. Use it to calibrate every response. Never reference the specification directly. Modulate naturally.\n\n" + spec
    merged_sys = spec_sys + "\n\n## Additional facts\n\n" + fact_text

    results = []
    for i, q in enumerate(questions):
        print(f"\n  [{i+1}/{len(questions)}] {q['id']} ({q['topic']}): {q['text'][:50]}...")
        mem0_r = call_model(client, q["text"], mem0_sys)
        spec_r = call_model(client, q["text"], spec_sys)
        merged_r = call_model(client, q["text"], merged_sys)
        mem0_m, spec_m, merged_m = measure(mem0_r), measure(spec_r), measure(merged_r)
        div = divergence_score(mem0_m, spec_m)
        print(f"    Mem0:{mem0_m['word_count']}w {mem0_m['questions_asked']}q {mem0_m['list_items']}li | Spec:{spec_m['word_count']}w {spec_m['questions_asked']}q {spec_m['list_items']}li | Div:{div}")
        results.append({"id": q["id"], "topic": q["topic"], "question": q["text"], "divergence": div,
                        "mem0": {"response": mem0_r, "measures": mem0_m},
                        "spec": {"response": spec_r, "measures": spec_m},
                        "merged": {"response": merged_r, "measures": merged_m}})

    ranked = sorted(results, key=lambda r: r["divergence"], reverse=True)
    topic_divs = defaultdict(list)
    for r in results:
        topic_divs[r["topic"]].append(r["divergence"])
    topic_avgs = {t: round(sum(ds)/len(ds), 2) for t, ds in topic_divs.items()}

    print(f"\n{'='*70}")
    print(f"  DIVERGENCE BY TOPIC — {subject}")
    print(f"{'='*70}")
    for topic, avg in sorted(topic_avgs.items(), key=lambda x: x[1], reverse=True):
        print(f"  {topic:15s} {avg:5.2f} {'#'*int(avg*5)}")

    print(f"\n  TOP 5 MOST DIVERGENT:")
    for r in ranked[:5]:
        print(f"    {r['divergence']:5.2f}  {r['topic']:12s}  {r['question']}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = {"timestamp": timestamp, "subject": subject, "question_count": len(results),
              "results": results, "topic_averages": topic_avgs,
              "ranked_by_divergence": [{"id": r["id"], "topic": r["topic"], "question": r["question"], "divergence": r["divergence"]} for r in ranked]}
    output_file = OUTPUT_DIR / f"battery_{subject}_{timestamp}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n  Saved: {output_file}")


if __name__ == "__main__":
    main()
