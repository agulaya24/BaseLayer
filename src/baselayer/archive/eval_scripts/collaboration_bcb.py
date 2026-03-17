"""
Human-Machine Collaboration BCB Study
======================================
Tests whether a compressed project identity brief helps AI collaborate
more effectively than raw documentation alone.

Subject: Base Layer project itself
Hypothesis: System X + Base Layer > System X alone — applied to the project's own identity

Conditions:
  C1: No context (bare Sonnet)
  C2: CLAUDE.md only (handcrafted session bootstrap)
  C3: Compressed brief only (pipeline-generated baselayer_meta brief)
  C4: CLAUDE.md + Compressed brief (stacked)

Tasks: 20 questions with known correct answers from DECISIONS.md, design principles,
       and documented DO NOT rules. Each answer has mechanical ground-truth keywords.

Scoring: Mechanical keyword matching + decision number matching. No LLM judge.
  - Each task has required_keywords (must contain) and forbidden_keywords (must NOT contain)
  - Score = (required_hits / required_total) * 100, penalized by forbidden_hits
  - Binary correctness threshold: >= 70% of required keywords present

Cost: ~$2-4 total (4 conditions × 20 tasks × Sonnet)
"""

import sys
import os
import json
import re
import time
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))
from api_client import call_api

_HOME = Path.home() / "Anthropic"
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "docs", "eval", "collaboration_bcb")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ============================================================
# LOAD IDENTITY MATERIALS
# ============================================================

def load_claude_md():
    path = str(_HOME / "CLAUDE.md")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def load_brief():
    path = str(_HOME / "subjects" / "baselayer_meta" / "data" / "identity_layers" / "brief_v4.md")
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            text = text[end + 3:].strip()
    return text.replace("## Injectable Block\n\n", "").replace("## Injectable Block\n", "")

def load_core():
    path = str(_HOME / "subjects" / "baselayer_meta" / "data" / "identity_layers" / "core_v4.md")
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    if "## Injectable Block" in text:
        text = text[text.index("## Injectable Block"):]
    return text

def load_anchors():
    path = str(_HOME / "subjects" / "baselayer_meta" / "data" / "identity_layers" / "anchors_v4.md")
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    if "## Injectable Block" in text:
        text = text[text.index("## Injectable Block"):]
    return text

def load_predictions():
    path = str(_HOME / "subjects" / "baselayer_meta" / "data" / "identity_layers" / "predictions_v4.md")
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    if "## Injectable Block" in text:
        text = text[text.index("## Injectable Block"):]
    return text

# ============================================================
# TASK DEFINITIONS
# 20 tasks with ground-truth answers from documented decisions
# ============================================================

TASKS = [
    # === DO NOT violations (should the model know what to avoid?) ===
    {
        "id": "T01",
        "category": "do_not",
        "question": "We need to generate narrative text for a subject's identity layer. Should we use Qwen 2.5 14B via Ollama for this since it's free?",
        "ground_truth": "No. Qwen has failed 12 times for narrative generation (D-030). Use it for extraction only.",
        "required_keywords": ["no", "fail", "extraction"],
        "forbidden_keywords": [],
        "decision_ref": "D-030",
    },
    {
        "id": "T02",
        "category": "do_not",
        "question": "I'm generating the PREDICTIONS identity layer. I have the ANCHORS layer output available. Should I show it to Sonnet as reference to ensure consistency?",
        "ground_truth": "No. Showing prior layer output to Sonnet during regeneration causes 26% anchoring bias. Blind regen only (D-053).",
        "required_keywords": ["no", "anchor", "blind"],
        "forbidden_keywords": [],
        "decision_ref": "D-053",
    },
    {
        "id": "T03",
        "category": "do_not",
        "question": "The brief currently says 'this person uses Bayesian reasoning and epistemic humility frameworks.' Is this good?",
        "ground_truth": "No. Philosophy framework names should never appear in identity blocks (D-041). Frameworks inform process, never appear in output.",
        "required_keywords": ["no", "framework"],
        "forbidden_keywords": [],
        "decision_ref": "D-041",
    },
    {
        "id": "T04",
        "category": "do_not",
        "question": "I want to re-extract facts for a subject. I've cleared the SQLite memory_facts table. Ready to go?",
        "ground_truth": "No. Must also clear ChromaDB vectors. Old vectors cause AUDN to NOOP on legitimate new facts (S65).",
        "required_keywords": ["no", "chromadb", "vector"],
        "forbidden_keywords": [],
        "decision_ref": "S65",
    },
    {
        "id": "T05",
        "category": "do_not",
        "question": "The brief says 'Base Layer is a 14-step pipeline that processes conversations into behavioral models.' Should the brief reference what built it?",
        "ground_truth": "No. Brief describes WHO, not WHAT built the brief. No self-reference in brief (S62b).",
        "required_keywords": ["no", "self-reference", "who"],
        "forbidden_keywords": [],
        "decision_ref": "S62b",
    },

    # === Architecture decisions ===
    {
        "id": "T06",
        "category": "architecture",
        "question": "What model should we use for fact extraction?",
        "ground_truth": "Haiku for extraction. Use the cheapest model that can do the job.",
        "required_keywords": ["haiku"],
        "forbidden_keywords": [],
        "decision_ref": "pipeline",
    },
    {
        "id": "T07",
        "category": "architecture",
        "question": "What model should we use for knowledge tier classification?",
        "ground_truth": "Sonnet for tiering (reclassify_tiers.py). Haiku for fact_type classification.",
        "required_keywords": ["sonnet"],
        "forbidden_keywords": [],
        "decision_ref": "pipeline",
    },
    {
        "id": "T08",
        "category": "architecture",
        "question": "What is the final artifact of the pipeline — the layers or the brief?",
        "ground_truth": "The brief is the final artifact. Layers are intermediate. Unified brief preferred everywhere.",
        "required_keywords": ["brief", "final"],
        "forbidden_keywords": [],
        "decision_ref": "S62b",
    },
    {
        "id": "T09",
        "category": "architecture",
        "question": "How does ChromaDB compute similarity in this system?",
        "ground_truth": "ChromaDB uses L2 distance, not cosine. Correct formula: sim = 1 - dist^2/2.",
        "required_keywords": ["l2"],
        "forbidden_keywords": [],
        "decision_ref": "S68",
    },
    {
        "id": "T10",
        "category": "architecture",
        "question": "When processing non-conversation text like patents or autobiographies, what flags do I need?",
        "ground_truth": "--document-mode for extraction, --subject 'Name' for tiering.",
        "required_keywords": ["document-mode", "subject"],
        "forbidden_keywords": [],
        "decision_ref": "S68",
    },

    # === Design philosophy ===
    {
        "id": "T11",
        "category": "philosophy",
        "question": "Two facts about a subject contradict each other. Should we delete the older one?",
        "ground_truth": "No. Contradictions are diagnostic information about identity complexity, not problems to resolve. Preserve both sides with confidence scores.",
        "required_keywords": ["no", "contradict", "preserv"],
        "forbidden_keywords": ["delete", "remove"],
        "decision_ref": "D-021/D-036",
    },
    {
        "id": "T12",
        "category": "philosophy",
        "question": "How should Base Layer be positioned relative to existing memory systems like Mem0 and Supermemory?",
        "ground_truth": "Base Layer is the identity layer that sits ON TOP of memory, not a replacement. Memory providers are potential integration partners, not competitors. Never denigrate the existing ecosystem.",
        "required_keywords": ["on top", "partner"],
        "forbidden_keywords": ["replac", "better than"],
        "decision_ref": "S68",
    },
    {
        "id": "T13",
        "category": "philosophy",
        "question": "The system will never perfectly model someone. Is this a bug or a feature?",
        "ground_truth": "Feature. Foundational principle: Inherent Incompleteness. The system will never have a complete or fully accurate picture. Neither will the person. Neither will anyone else.",
        "required_keywords": ["incomplet", "never", "complete"],
        "forbidden_keywords": [],
        "decision_ref": "D-023/D-024",
    },
    {
        "id": "T14",
        "category": "philosophy",
        "question": "Should we use an LLM-as-judge to evaluate brief quality?",
        "ground_truth": "Avoid. LLM judges conflate dimensions and can't distinguish sound reasoning from stylistic mimicry. Use mechanical provenance-traced evaluation instead.",
        "required_keywords": ["avoid", "mechanic"],
        "forbidden_keywords": [],
        "decision_ref": "D-073",
    },
    {
        "id": "T15",
        "category": "philosophy",
        "question": "A user corrects the system about themselves: 'I actually don't value efficiency, I value thoroughness.' What happens?",
        "ground_truth": "User is highest authority on their own identity (D-019). Correction is stored as new data. User corrections are definitive truth.",
        "required_keywords": ["user", "authorit", "correct"],
        "forbidden_keywords": [],
        "decision_ref": "D-019/D-021",
    },

    # === Novel situations (requires deep understanding) ===
    {
        "id": "T16",
        "category": "novel",
        "question": "Someone wants to run the pipeline on their Slack messages. The pipeline currently supports ChatGPT exports, Claude exports, journals, and text files. What's the right approach?",
        "ground_truth": "Import as text files or directory. The pipeline processes any text — extraction doesn't care about source format. Use document-mode if not conversation-structured.",
        "required_keywords": ["text", "import"],
        "forbidden_keywords": [],
        "decision_ref": "general",
    },
    {
        "id": "T17",
        "category": "novel",
        "question": "Sonnet tiering on a patent corpus only classified 3.5% of facts as identity-tier. Most patents have behavioral patterns in them. What should we do?",
        "ground_truth": "Known issue — Sonnet tiering is too conservative for documents. Use rule-based promotion as workaround.",
        "required_keywords": ["conservative", "rule"],
        "forbidden_keywords": [],
        "decision_ref": "S68",
    },
    {
        "id": "T18",
        "category": "novel",
        "question": "We want to evaluate whether compression amplifies signal. What's the evidence so far?",
        "ground_truth": "On Franklin, compressed brief outperformed full structured data by +0.40 points (C5c wins). On User A, C5c retained ~97% of C2. N=2, need more data. Compression may amplify, not just save tokens.",
        "required_keywords": ["franklin", "c5c", "amplif"],
        "forbidden_keywords": [],
        "decision_ref": "eval",
    },
    {
        "id": "T19",
        "category": "novel",
        "question": "If Anthropic adds 'Generate behavioral summary' to Claude's native memory next month, what's Base Layer's unique value?",
        "ground_truth": "Provenance (every claim traces to evidence), auditability (transparent reasoning chains), portability (works across providers), multi-source pipeline (any text, not just conversations), open research.",
        "required_keywords": ["provenance", "audit"],
        "forbidden_keywords": [],
        "decision_ref": "platform_risk",
    },
    {
        "id": "T20",
        "category": "novel",
        "question": "A community member submits a PR that adds a 15th pipeline step: 'sentiment analysis' that scores each fact for emotional valence. Should we merge it?",
        "ground_truth": "Likely not. The pipeline is already potentially overengineered (14 steps, no ablation data). Adding steps without ablation data on existing steps contradicts the research approach. Also: the system explicitly cannot model emotions — text reveals reasoning patterns, not emotional states.",
        "required_keywords": ["emotion", "ablation"],
        "forbidden_keywords": [],
        "decision_ref": "D-023/meta_review",
    },
]

# ============================================================
# CONDITIONS
# ============================================================

def build_conditions():
    claude_md = load_claude_md()
    brief = load_brief()

    return {
        "C1_bare": {
            "name": "No context",
            "system": "You are a helpful AI assistant.",
        },
        "C2_claude_md": {
            "name": "CLAUDE.md only",
            "system": f"You are an AI assistant helping with the Base Layer project. Here is your session bootstrap:\n\n{claude_md}",
        },
        "C3_brief": {
            "name": "Compressed brief only",
            "system": f"You are an AI assistant helping with the Base Layer project. Here is the project's behavioral identity brief:\n\n{brief}",
        },
        "C4_stacked": {
            "name": "CLAUDE.md + brief (stacked)",
            "system": f"You are an AI assistant helping with the Base Layer project.\n\nSESSION BOOTSTRAP:\n{claude_md}\n\nPROJECT IDENTITY BRIEF:\n{brief}",
        },
    }

# ============================================================
# MECHANICAL SCORING
# ============================================================

def score_response(response_text, task):
    """Score a response mechanically against ground truth keywords."""
    text_lower = response_text.lower()

    # Required keyword hits
    required = task["required_keywords"]
    required_hits = sum(1 for kw in required if kw.lower() in text_lower)
    required_total = len(required)
    required_rate = required_hits / max(required_total, 1)

    # Forbidden keyword hits (penalty)
    forbidden = task.get("forbidden_keywords", [])
    forbidden_hits = sum(1 for kw in forbidden if kw.lower() in text_lower)

    # Decision reference check (bonus)
    decision_ref = task.get("decision_ref", "")
    ref_found = decision_ref.lower() in text_lower if decision_ref and decision_ref != "general" else False

    # Composite score
    base_score = required_rate * 100
    penalty = forbidden_hits * 15  # -15 per forbidden keyword
    bonus = 10 if ref_found else 0
    final_score = max(0, min(100, base_score - penalty + bonus))

    return {
        "required_hits": required_hits,
        "required_total": required_total,
        "required_rate": round(required_rate, 3),
        "forbidden_hits": forbidden_hits,
        "ref_found": ref_found,
        "score": round(final_score, 1),
        "correct": required_rate >= 0.70 and forbidden_hits == 0,
    }


# ============================================================
# RUNNER
# ============================================================

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(os.path.join(OUTPUT_DIR, "run_log.txt"), "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_task(condition_id, condition_data, task):
    """Run one task under one condition."""
    try:
        resp = call_api(
            model="claude-sonnet-4-20250514",
            system=condition_data["system"],
            messages=[{"role": "user", "content": task["question"]}],
            max_tokens=1024,
            temperature=0,
            caller=f"collab_bcb_{condition_id}_{task['id']}",
        )
        response_text = resp.content[0].text
        scores = score_response(response_text, task)

        return {
            "task_id": task["id"],
            "condition": condition_id,
            "category": task["category"],
            "question": task["question"],
            "response": response_text[:500],
            "response_full_chars": len(response_text),
            "scores": scores,
            "correct": scores["correct"],
        }
    except Exception as e:
        log(f"  ERROR: {condition_id}/{task['id']}: {e}")
        return {
            "task_id": task["id"],
            "condition": condition_id,
            "error": str(e),
            "correct": False,
        }


def main():
    log("=" * 70)
    log("HUMAN-MACHINE COLLABORATION BCB STUDY")
    log("=" * 70)
    log(f"Tasks: {len(TASKS)}")
    log(f"Conditions: C1 (bare), C2 (CLAUDE.md), C3 (brief), C4 (stacked)")

    conditions = build_conditions()
    log(f"Context sizes: C1={len(conditions['C1_bare']['system'])} chars, "
        f"C2={len(conditions['C2_claude_md']['system'])} chars, "
        f"C3={len(conditions['C3_brief']['system'])} chars, "
        f"C4={len(conditions['C4_stacked']['system'])} chars")

    all_results = {
        "meta": {
            "study": "Human-Machine Collaboration BCB",
            "subject": "Base Layer project identity",
            "hypothesis": "Compressed project identity brief helps AI collaborate more effectively than raw docs alone",
            "started": datetime.now().isoformat(),
            "tasks": len(TASKS),
            "conditions": 4,
        },
        "results": [],
        "by_condition": {},
        "by_category": {},
    }

    # Run all conditions × all tasks
    for cid, cdata in conditions.items():
        log(f"\n{'='*70}")
        log(f"CONDITION: {cid} — {cdata['name']}")
        log(f"{'='*70}")

        condition_results = []
        correct_count = 0

        for i, task in enumerate(TASKS):
            log(f"  [{i+1}/{len(TASKS)}] {task['id']}: {task['question'][:60]}...")
            result = run_task(cid, cdata, task)
            condition_results.append(result)
            all_results["results"].append(result)

            if result.get("correct"):
                correct_count += 1
                log(f"    CORRECT (score={result['scores']['score']})")
            else:
                score_info = result.get("scores", {})
                log(f"    WRONG (score={score_info.get('score', '?')}, "
                    f"hits={score_info.get('required_hits', '?')}/{score_info.get('required_total', '?')})")

        accuracy = correct_count / len(TASKS)
        avg_score = sum(r.get("scores", {}).get("score", 0) for r in condition_results) / len(TASKS)

        all_results["by_condition"][cid] = {
            "name": cdata["name"],
            "correct": correct_count,
            "total": len(TASKS),
            "accuracy": round(accuracy, 3),
            "avg_score": round(avg_score, 1),
        }

        log(f"\n  {cid} SUMMARY: {correct_count}/{len(TASKS)} correct ({accuracy:.0%}), avg score={avg_score:.1f}")

    # Category breakdown
    categories = set(t["category"] for t in TASKS)
    for cat in categories:
        cat_results = {}
        for cid in conditions:
            cat_correct = sum(1 for r in all_results["results"]
                            if r["condition"] == cid and r["category"] == cat and r.get("correct"))
            cat_total = sum(1 for t in TASKS if t["category"] == cat)
            cat_results[cid] = {"correct": cat_correct, "total": cat_total,
                               "accuracy": round(cat_correct / max(cat_total, 1), 3)}
        all_results["by_category"][cat] = cat_results

    # ============================================================
    # ANALYSIS
    # ============================================================
    log("\n" + "=" * 70)
    log("ANALYSIS")
    log("=" * 70)

    log("\nOVERALL ACCURACY:")
    for cid, data in all_results["by_condition"].items():
        bar = "#" * int(data["accuracy"] * 30)
        log(f"  {cid:<15} {data['correct']:>2}/{data['total']} ({data['accuracy']:.0%}) {bar}  avg={data['avg_score']:.1f}")

    log("\nBY CATEGORY:")
    for cat in sorted(categories):
        log(f"  {cat}:")
        for cid in conditions:
            data = all_results["by_category"][cat][cid]
            log(f"    {cid:<15} {data['correct']}/{data['total']} ({data['accuracy']:.0%})")

    # Stacking analysis
    c1 = all_results["by_condition"]["C1_bare"]["accuracy"]
    c2 = all_results["by_condition"]["C2_claude_md"]["accuracy"]
    c3 = all_results["by_condition"]["C3_brief"]["accuracy"]
    c4 = all_results["by_condition"]["C4_stacked"]["accuracy"]

    log("\nSTACKING ANALYSIS:")
    log(f"  C1 (bare):     {c1:.0%}")
    log(f"  C2 (CLAUDE.md): {c2:.0%}  delta from bare: {'+' if c2-c1>=0 else ''}{(c2-c1):.0%}")
    log(f"  C3 (brief):    {c3:.0%}  delta from bare: {'+' if c3-c1>=0 else ''}{(c3-c1):.0%}")
    log(f"  C4 (stacked):  {c4:.0%}  delta from bare: {'+' if c4-c1>=0 else ''}{(c4-c1):.0%}")
    log(f"  C4 vs C2:      {'+' if c4-c2>=0 else ''}{(c4-c2):.0%} (does brief ADD to CLAUDE.md?)")
    log(f"  C4 vs C3:      {'+' if c4-c3>=0 else ''}{(c4-c3):.0%} (does CLAUDE.md ADD to brief?)")

    if c4 > c2 and c4 > c3:
        log("  VERDICT: STACKING WORKS — C4 > both C2 and C3 individually")
    elif c4 > max(c2, c3):
        log("  VERDICT: STACKING HELPS — C4 > best individual condition")
    elif c2 > c3:
        log("  VERDICT: CLAUDE.md > brief — handcrafted beats compressed for this subject")
    elif c3 > c2:
        log("  VERDICT: Brief > CLAUDE.md — compressed beats handcrafted for this subject")
    else:
        log("  VERDICT: TIE — no clear winner")

    # Per-task breakdown for wrong answers
    log("\nMISSED TASKS (by condition):")
    for cid in conditions:
        missed = [r for r in all_results["results"]
                 if r["condition"] == cid and not r.get("correct")]
        if missed:
            log(f"  {cid}:")
            for r in missed:
                log(f"    {r['task_id']}: {r.get('scores', {}).get('required_hits', '?')}/{r.get('scores', {}).get('required_total', '?')} keywords")

    all_results["meta"]["completed"] = datetime.now().isoformat()
    all_results["stacking"] = {
        "c1_bare": c1, "c2_claude_md": c2, "c3_brief": c3, "c4_stacked": c4,
        "brief_adds_to_claude_md": round(c4 - c2, 3),
        "claude_md_adds_to_brief": round(c4 - c3, 3),
        "stacking_works": c4 > c2 and c4 > c3,
    }

    path = os.path.join(OUTPUT_DIR, "collaboration_bcb_results.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
    log(f"\nResults saved: {path}")

    return all_results


if __name__ == "__main__":
    main()
