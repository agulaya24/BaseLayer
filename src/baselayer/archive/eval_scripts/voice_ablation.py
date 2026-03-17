"""
Voice & Framing Ablation — Which brief structure produces the best output?
Same facts, different voice/structure. Mechanical scoring.

Conditions:
  A: Current 3-layer compose (baseline — existing brief)
  B: CORE-dominant (operational guidance voice, anchors+predictions woven in)
  C: Pure directive (every sentence is an instruction to the AI)
  D: Pure narrative (third-person behavioral description)
  E: Annotated guide (CORE voice with section headers and explicit "when X, do Y")

Subject: Franklin (135 identity-tier facts)
Scoring: Embedding coverage + cross-prediction + pattern density (mechanical, no LLM judge)
Cost: ~$1-2 (Sonnet brief generation × 4 new conditions, baseline is free)
"""

import sys
import os
import json
import re
import numpy as np
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))
from api_client import call_api

_HOME = str(Path.home() / "Anthropic")
FRANKLIN_DB = os.path.join(_HOME, "subjects", "franklin_memory", "data", "database", "memory.db")
FRANKLIN_BRIEF = os.path.join(_HOME, "subjects", "franklin_memory", "data", "identity_layers", "brief_v4.md")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "docs", "eval", "voice_ablation")
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("Loading embedding model...")
from sentence_transformers import SentenceTransformer
EMBED_MODEL = SentenceTransformer('all-MiniLM-L6-v2')
print("Ready.")

import sqlite3

def load_facts():
    conn = sqlite3.connect(FRANKLIN_DB)
    rows = conn.execute("""
        SELECT id, fact_text, fact_type, knowledge_tier, predicate, object_text, subject
        FROM memory_facts WHERE superseded_by IS NULL AND knowledge_tier = 'identity'
        ORDER BY id
    """).fetchall()
    conn.close()
    return [{"id": r[0], "fact_text": r[1], "fact_type": r[2], "knowledge_tier": r[3],
             "predicate": r[4], "object_text": r[5], "subject": r[6]} for r in rows]

def load_baseline():
    with open(FRANKLIN_BRIEF, "r", encoding="utf-8") as f:
        text = f.read()
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1: text = text[end + 3:].strip()
    return text.replace("## Injectable Block\n\n", "").replace("## Injectable Block\n", "")

def embed_texts(texts):
    if not texts: return np.array([])
    vecs = EMBED_MODEL.encode(texts, show_progress_bar=False)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return vecs / norms

def score_brief(brief_text, all_facts):
    if not brief_text: return {"composite": 0}
    brief_vec = embed_texts([brief_text])[0]
    fact_vecs = embed_texts([f["fact_text"] for f in all_facts])
    sims = [float(np.dot(brief_vec, fv)) for fv in fact_vecs]
    m1 = round(float(np.mean(sims)), 4)
    m2 = round(sum(1 for s in sims if s > 0.45) / len(sims), 4)

    text_lower = brief_text.lower()
    patterns = [r'\bwhen\b.*\b(he|they|this person)\b', r'\bif\b.*\b(he|they)\b',
                r'\btend[s]?\s+to\b', r'\bwill\s+(likely|often|always)\b',
                r'\bdefault[s]?\s+to\b', r'\brather\s+than\b', r'\bnever\b',
                r'\balways\b', r'\bfailure\s+mode\b', r'\bblind\s+spot\b']
    m3 = round(sum(len(re.findall(p, text_lower)) for p in patterns) / (len(brief_text)/1000), 2)

    composite = round(m1 * 40 + m2 * 25 + min(m3/10, 1) * 15 + 10, 2)  # +10 base
    return {"m1_coverage": m1, "m2_prediction": m2, "m3_pattern_density": m3,
            "composite": composite, "chars": len(brief_text), "tokens_est": len(brief_text)//4}

# Voice prompts — same facts, different framing
VOICES = {
    "B_core_dominant": {
        "name": "CORE-dominant (operational guidance)",
        "system": """You generate behavioral briefs in an OPERATIONAL GUIDANCE voice.
The brief is injected into an AI's system prompt so it understands how to work with this person.

VOICE: Write as if you're briefing a colleague on how to collaborate with this person.
Use "they" pronouns. Refer to subject as "this person" or "they."
Structure naturally — no section headers. Weave axioms, behaviors, and predictions together
into flowing operational guidance. When you describe a belief, immediately follow with
how it manifests in behavior and what to expect.

Every sentence should change how an AI responds. No biography. No filler.
Target: 2000-3000 characters.""",
    },
    "C_pure_directive": {
        "name": "Pure directive (instructions to AI)",
        "system": """You generate behavioral briefs as DIRECT INSTRUCTIONS to an AI.
The brief is injected into an AI's system prompt.

VOICE: Every sentence is an imperative instruction. "Do X." "Never Y." "When they Z, respond with W."
Use second person addressing the AI: "You should...", "Expect them to...", "Do not..."
No description, no narrative — pure directives.

Structure as a prioritized instruction set. Most important directives first.
Use he/him pronouns for the subject.
Target: 1500-2500 characters.""",
    },
    "D_pure_narrative": {
        "name": "Pure narrative (third-person description)",
        "system": """You generate behavioral briefs as THIRD-PERSON NARRATIVE.
The brief is injected into an AI's system prompt.

VOICE: Write as a psychologist's case study. Third-person, analytical, descriptive.
"He tends to...", "His reasoning pattern involves...", "When confronted with X, he typically..."
No directives, no instructions — pure behavioral description.

Use he/him pronouns. Refer to subject as "this person" or "he."
Focus on patterns, not biography. Show the person through their behaviors.
Target: 2000-3000 characters.""",
    },
    "E_annotated_guide": {
        "name": "Annotated guide (CORE voice + headers + when/do)",
        "system": """You generate behavioral briefs as an ANNOTATED COLLABORATION GUIDE.
The brief is injected into an AI's system prompt.

VOICE: Operational guidance with explicit section headers and trigger→response patterns.
Use clear headers like: REASONING PATTERNS, DECISION-MAKING, FAILURE MODES, ENGAGEMENT RULES.
Under each header, use "When [trigger], [what they do/what you should do]" format.
Weave in their core axioms as context for WHY the patterns exist.

Use he/him pronouns. Every section should change AI behavior.
Target: 2000-3000 characters.""",
    },
}

def generate_voice_brief(facts, voice_id, voice_data):
    fact_lines = "\n".join([f"- [{f['predicate']}] {f['fact_text']}" for f in facts])
    try:
        resp = call_api(
            model="claude-sonnet-4-20250514",
            system=voice_data["system"],
            messages=[{"role": "user", "content": f"Generate a behavioral brief from these {len(facts)} identity-tier facts:\n\n{fact_lines}"}],
            max_tokens=2048, temperature=0.3,
            caller=f"voice_ablation_{voice_id}",
        )
        return resp.content[0].text
    except Exception as e:
        print(f"  ERROR generating {voice_id}: {e}")
        return None

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(os.path.join(OUTPUT_DIR, "run_log.txt"), "a", encoding="utf-8") as f:
        f.write(line + "\n")

def main():
    log("=" * 70)
    log("VOICE & FRAMING ABLATION STUDY")
    log("=" * 70)

    facts = load_facts()
    baseline_brief = load_baseline()
    log(f"Facts: {len(facts)} identity-tier")
    log(f"Baseline brief: {len(baseline_brief)} chars")

    results = {
        "meta": {"subject": "franklin", "facts": len(facts), "started": datetime.now().isoformat()},
        "conditions": {},
    }

    # A: Baseline (existing production brief)
    log("\nA_baseline: Production brief (no generation)")
    scores_a = score_brief(baseline_brief, facts)
    results["conditions"]["A_baseline"] = {
        "name": "Production 3-layer compose (Opus)",
        "scores": scores_a, "composite": scores_a["composite"],
        "chars": len(baseline_brief), "brief_preview": baseline_brief[:300],
    }
    log(f"  composite={scores_a['composite']:.1f}  m1={scores_a['m1_coverage']:.3f}  m2={scores_a['m2_prediction']:.1%}  m3={scores_a['m3_pattern_density']:.1f}")

    # B-E: Generate + score
    for vid, vdata in VOICES.items():
        log(f"\n{vid}: {vdata['name']}")
        brief = generate_voice_brief(facts, vid, vdata)
        if not brief:
            results["conditions"][vid] = {"error": "generation failed"}
            continue
        scores = score_brief(brief, facts)
        results["conditions"][vid] = {
            "name": vdata["name"], "scores": scores, "composite": scores["composite"],
            "chars": len(brief), "brief_preview": brief[:300],
        }
        log(f"  composite={scores['composite']:.1f}  m1={scores['m1_coverage']:.3f}  m2={scores['m2_prediction']:.1%}  m3={scores['m3_pattern_density']:.1f}  chars={len(brief)}")

        # Save full brief
        with open(os.path.join(OUTPUT_DIR, f"{vid}_brief.md"), "w", encoding="utf-8") as f:
            f.write(brief)

    # Rankings
    log("\n" + "=" * 70)
    log("RANKINGS")
    log("=" * 70)
    ranked = sorted(results["conditions"].items(),
                    key=lambda x: x[1].get("composite", 0), reverse=True)
    for i, (vid, data) in enumerate(ranked):
        s = data.get("scores", {})
        log(f"  {i+1}. {vid:<25} composite={data.get('composite', 0):<8.1f} "
            f"m1={s.get('m1_coverage', 0):.3f}  m2={s.get('m2_prediction', 0):.3f}  "
            f"m3={s.get('m3_pattern_density', 0):.1f}  chars={data.get('chars', '?')}")

    baseline_composite = results["conditions"]["A_baseline"]["composite"]
    log("\nDELTAS FROM BASELINE:")
    for vid, data in results["conditions"].items():
        if vid == "A_baseline": continue
        delta = data.get("composite", 0) - baseline_composite
        log(f"  {vid}: {'+' if delta >= 0 else ''}{delta:.1f}")

    results["meta"]["completed"] = datetime.now().isoformat()
    path = os.path.join(OUTPUT_DIR, "voice_ablation_results.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    log(f"\nSaved: {path}")

if __name__ == "__main__":
    main()
