"""
Voice Downstream Evaluation — Test voice briefs on actual collaboration tasks.
Uses SONNET (not Qwen) as the downstream model to avoid Qwen-specific optimization.

Takes the 5 voice briefs from voice_ablation and tests them on collaboration BCB tasks.
This answers: does the annotated guide format actually help Sonnet answer project questions better?

Cost: ~$2-3 (Sonnet answering 20 tasks * 5 conditions = 100 API calls)
"""

import sys
import os
import json
import re
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))
from api_client import call_api

_HOME = str(Path.home() / "Anthropic")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "docs", "eval", "voice_downstream")
os.makedirs(OUTPUT_DIR, exist_ok=True)

VOICE_DIR = os.path.join(PROJECT_ROOT, "docs", "eval", "voice_ablation")
FRANKLIN_BRIEF = os.path.join(_HOME, "subjects", "franklin_memory", "data", "identity_layers", "brief_v4.md")

# 15 Franklin knowledge tasks — requires understanding Franklin's behavioral patterns
TASKS = [
    {"id": "F01", "category": "reasoning",
     "question": "Franklin is evaluating whether to invest in a new printing venture with a partner he doesn't fully trust. What would his approach be?",
     "required_keywords": ["frugality", "industry", "written", "document", "agreement", "clear terms"],
     "description": "Tests understanding of Franklin's approach to financial partnerships"},
    {"id": "F02", "category": "reasoning",
     "question": "Someone presents Franklin with a dogmatic philosophical argument. How does he respond?",
     "required_keywords": ["socratic", "question", "avoid", "dogmatic", "indirect", "humble"],
     "description": "Tests Socratic method and humility patterns"},
    {"id": "F03", "category": "failure_mode",
     "question": "Franklin has just achieved a major public success. What failure mode should you watch for?",
     "required_keywords": ["pride", "vanity", "humble", "struggle"],
     "description": "Tests knowledge of pride as his acknowledged weakness"},
    {"id": "F04", "category": "decision",
     "question": "Franklin must choose between a profitable private opportunity and a public service role. What does he choose and why?",
     "required_keywords": ["public", "benefit", "service", "useful", "honest"],
     "description": "Tests public benefit axiom"},
    {"id": "F05", "category": "reasoning",
     "question": "How does Franklin approach a scientific question about electricity?",
     "required_keywords": ["experiment", "systematic", "observation", "document", "share"],
     "description": "Tests systematic experimentation pattern"},
    {"id": "F06", "category": "interaction",
     "question": "You need to present a new idea to Franklin. What framing will be most effective?",
     "required_keywords": ["public", "benefit", "practical", "utility"],
     "description": "Tests engagement rules"},
    {"id": "F07", "category": "failure_mode",
     "question": "Franklin is asked to organize a complex multi-step project. Where will he struggle?",
     "required_keywords": ["order", "organiz", "struggle", "weakness"],
     "description": "Tests Order as admitted weakness"},
    {"id": "F08", "category": "decision",
     "question": "A financial deal looks good but the terms are vague. What does Franklin insist on?",
     "required_keywords": ["clear", "terms", "written", "agreement", "exploit", "decei"],
     "description": "Tests financial exploitation sensitivity (Keith experience)"},
    {"id": "F09", "category": "reasoning",
     "question": "Franklin encounters a dispute between two colleagues. How does he mediate?",
     "required_keywords": ["harmony", "goodwill", "avoid", "dispute", "written"],
     "description": "Tests conflict avoidance + written communication preference"},
    {"id": "F10", "category": "interaction",
     "question": "Franklin seems withdrawn and quiet in a meeting. What's happening and how should you respond?",
     "required_keywords": ["reflect", "processing", "space", "avoid", "dispute"],
     "description": "Tests engagement rules for withdrawal"},
    {"id": "F11", "category": "decision",
     "question": "Franklin is considering whether to patent his new stove design. What does he decide?",
     "required_keywords": ["public", "benefit", "share", "free", "not patent"],
     "description": "Tests sharing discoveries for public benefit"},
    {"id": "F12", "category": "reasoning",
     "question": "Franklin needs to persuade a colonial legislature to fund defense. What strategy does he use?",
     "required_keywords": ["voluntary", "persua", "written", "consensus", "anonymous"],
     "description": "Tests persuasion through writing and consensus-building"},
    {"id": "F13", "category": "failure_mode",
     "question": "Franklin is reviewing a colleague's work and finds significant errors. How does he deliver the feedback?",
     "required_keywords": ["indirect", "gentle", "socratic", "question", "suggest"],
     "description": "Tests Socratic approach to disagreement"},
    {"id": "F14", "category": "interaction",
     "question": "What kind of leisure activity would Franklin appreciate vs. reject?",
     "required_keywords": ["refined", "read", "intellectual", "avoid", "tavern", "frivolous"],
     "description": "Tests specific preference knowledge"},
    {"id": "F15", "category": "decision",
     "question": "Franklin's self-improvement system has failed to produce results on one virtue for weeks. How does he respond?",
     "required_keywords": ["systematic", "track", "virtue", "persist", "practice"],
     "description": "Tests systematic self-improvement commitment"},
]


def load_voice_briefs():
    """Load all voice briefs from voice_ablation output."""
    briefs = {}

    # A: Production baseline
    if os.path.exists(FRANKLIN_BRIEF):
        with open(FRANKLIN_BRIEF, "r", encoding="utf-8") as f:
            text = f.read()
        if text.startswith("---"):
            end = text.find("---", 3)
            if end != -1: text = text[end + 3:].strip()
        briefs["A_baseline"] = text.replace("## Injectable Block\n\n", "").replace("## Injectable Block\n", "")

    # B-E: Generated briefs
    for voice_id in ["B_core_dominant", "C_pure_directive", "D_pure_narrative", "E_annotated_guide"]:
        path = os.path.join(VOICE_DIR, f"{voice_id}_brief.md")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                briefs[voice_id] = f.read()

    return briefs


def ask_sonnet(question, brief_text):
    """Ask Sonnet a question with a brief injected as system context."""
    system = f"""You are an AI assistant helping someone work with a specific person.
Here is what you know about this person:

{brief_text}

Answer questions about how to work with this person based ONLY on this context.
Be specific and practical. Reference specific behavioral patterns from the brief."""

    try:
        resp = call_api(
            model="claude-sonnet-4-20250514",
            system=system,
            messages=[{"role": "user", "content": question}],
            max_tokens=500, temperature=0.2,
            caller="voice_downstream",
        )
        return resp.content[0].text
    except Exception as e:
        return f"ERROR: {e}"


def score_response(response, task):
    """Mechanical scoring of response against task requirements."""
    resp_lower = response.lower()

    # Keyword hits
    hits = 0
    matched = []
    for kw in task["required_keywords"]:
        if kw.lower() in resp_lower:
            hits += 1
            matched.append(kw)

    keyword_score = hits / len(task["required_keywords"]) if task["required_keywords"] else 0

    # Specificity: non-generic content ratio
    generic_phrases = ["in general", "it depends", "there are many", "various factors",
                       "it's important to", "one should", "it's worth noting"]
    generic_count = sum(1 for p in generic_phrases if p in resp_lower)

    # Length penalty for very short or very long responses
    words = len(response.split())
    length_bonus = 1.0 if 50 <= words <= 200 else 0.8

    # Behavioral pattern detection (evidence the response uses the brief)
    pattern_markers = [r'\bwhen\b', r'\btend', r'\bfailure', r'\bstruggle',
                       r'\baxiom', r'\bpattern', r'\bapproach']
    pattern_count = sum(1 for p in pattern_markers if re.search(p, resp_lower))
    pattern_bonus = min(pattern_count / 3, 1.0) * 0.1

    score = keyword_score * 0.7 + (1 - min(generic_count/3, 1)) * 0.1 + length_bonus * 0.1 + pattern_bonus
    return {
        "keyword_score": round(keyword_score, 3),
        "keywords_matched": matched,
        "keywords_total": len(task["required_keywords"]),
        "generic_count": generic_count,
        "word_count": words,
        "pattern_count": pattern_count,
        "total_score": round(score, 3),
    }


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(os.path.join(OUTPUT_DIR, "run_log.txt"), "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main():
    log("=" * 70)
    log("VOICE DOWNSTREAM EVALUATION — Sonnet on Collaboration Tasks")
    log("=" * 70)

    briefs = load_voice_briefs()
    log(f"Loaded {len(briefs)} voice briefs: {list(briefs.keys())}")
    for vid, b in briefs.items():
        log(f"  {vid}: {len(b)} chars")

    results = {"meta": {"started": datetime.now().isoformat(), "tasks": len(TASKS),
                        "voices": list(briefs.keys()), "model": "claude-sonnet-4-20250514"},
               "conditions": {}}

    for vid, brief in briefs.items():
        log(f"\n{'=' * 50}")
        log(f"CONDITION: {vid} ({len(brief)} chars)")
        log(f"{'=' * 50}")

        condition_results = []
        total_score = 0

        for task in TASKS:
            log(f"  {task['id']}: {task['category']} — {task['description']}")
            response = ask_sonnet(task["question"], brief)
            scoring = score_response(response, task)
            total_score += scoring["total_score"]

            condition_results.append({
                "task_id": task["id"],
                "category": task["category"],
                "score": scoring,
                "response_preview": response[:200],
            })
            log(f"    score={scoring['total_score']:.2f}  keywords={scoring['keywords_matched']}")

        avg_score = total_score / len(TASKS)
        results["conditions"][vid] = {
            "brief_chars": len(brief),
            "avg_score": round(avg_score, 3),
            "total_score": round(total_score, 2),
            "tasks": condition_results,
            "by_category": {},
        }

        # Category breakdown
        categories = set(t["category"] for t in TASKS)
        for cat in categories:
            cat_tasks = [r for r in condition_results if r["category"] == cat]
            cat_avg = sum(r["score"]["total_score"] for r in cat_tasks) / len(cat_tasks) if cat_tasks else 0
            results["conditions"][vid]["by_category"][cat] = round(cat_avg, 3)

        log(f"  AVG SCORE: {avg_score:.3f}")

    # Rankings
    log("\n" + "=" * 70)
    log("RANKINGS")
    log("=" * 70)
    ranked = sorted(results["conditions"].items(), key=lambda x: x[1]["avg_score"], reverse=True)
    for i, (vid, data) in enumerate(ranked):
        log(f"  {i+1}. {vid:<25} avg={data['avg_score']:.3f}  chars={data['brief_chars']}")

    # Category winner
    log("\nBEST PER CATEGORY:")
    categories = set(t["category"] for t in TASKS)
    for cat in sorted(categories):
        best_vid = max(results["conditions"].items(),
                       key=lambda x: x[1]["by_category"].get(cat, 0))
        log(f"  {cat}: {best_vid[0]} ({best_vid[1]['by_category'].get(cat, 0):.3f})")

    results["meta"]["completed"] = datetime.now().isoformat()
    path = os.path.join(OUTPUT_DIR, "voice_downstream_results.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    log(f"\nSaved: {path}")


if __name__ == "__main__":
    main()
