"""
Collective Decision: C28 vs C31 — Which is the production compose prompt?

Sends all 6 briefs (C28 × 3 subjects + C31 × 3 subjects) to Opus for head-to-head evaluation.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from api_client import get_anthropic_client

OPUS = "claude-opus-4-20250514"

SUBJECTS = [
    ("franklin", "C:/Users/Aarik/Anthropic/subjects/franklin_memory"),
    ("buffett", "C:/Users/Aarik/Anthropic/subjects/buffett_memory"),
    ("aarik", "C:/Users/Aarik/Anthropic/memory_system_v4"),
]

DECISION_PROMPT = """You are the Collective — a panel of behavioral brief evaluators making a production decision.

You must choose between two compose prompt conditions (C28 and C31) for the Base Layer production pipeline. Both produce behavioral briefs that an LLM reads before every interaction with a person.

Below are the briefs produced by each condition across 3 subjects (Franklin, Buffett, Aarik). You also have the source layers for verification.

EVALUATION CRITERIA (the 4 primitives):
1. PROVENANCE — Can the LLM explain HOW it knows each claim? Citations trace to source?
2. BEHAVIORAL CHANGE — Does the brief change LLM behavior? Directives, communication guidance?
3. EPISTEMIC CALIBRATION — Does the brief know what it doesn't know? FP warnings, CANNOT PREDICT, temporal awareness?
4. SIGNAL DENSITY — No noise, no redundancy, every sentence adds understanding?

ADDITIONAL CRITERIA for production selection:
- Consistency across subjects (low variance preferred)
- Robustness with thin vs rich source data
- FP warning faithfulness (paraphrased from source = faithful, not fabricated)
- Format appropriateness for each subject

Previous scoring (provenance-corrected rubric, /90):
C28: Franklin 88, Buffett 83, Aarik 82 — avg 84.3
C31: Franklin 83, Buffett 85, Aarik 83 — avg 83.7

===== SOURCE LAYERS: FRANKLIN =====
{franklin_layers}

===== C28 FRANKLIN =====
{c28_franklin}

===== C31 FRANKLIN =====
{c31_franklin}

===== SOURCE LAYERS: BUFFETT =====
{buffett_layers}

===== C28 BUFFETT =====
{c28_buffett}

===== C31 BUFFETT =====
{c31_buffett}

===== SOURCE LAYERS: AARIK =====
{aarik_layers}

===== C28 AARIK =====
{c28_aarik}

===== C31 AARIK =====
{c31_aarik}

Make your decision. Output a JSON object:
{{
    "winner": "C28" or "C31",
    "confidence": "high" or "medium" or "low",
    "reasoning": "2-3 sentences explaining the decision",
    "franklin_preference": "C28" or "C31" or "tie",
    "franklin_note": "1 sentence",
    "buffett_preference": "C28" or "C31" or "tie",
    "buffett_note": "1 sentence",
    "aarik_preference": "C28" or "C31" or "tie",
    "aarik_note": "1 sentence",
    "production_recommendation": "The specific prompt to use and any modifications"
}}"""


def load_layer(subject_dir, filename):
    path = os.path.join(subject_dir, "data", "identity_layers", filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def load_brief(subject_dir, condition):
    path = os.path.join(subject_dir, "data", "identity_layers", f"brief_ablation_{condition}.md")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def format_layers(subject_dir):
    a = load_layer(subject_dir, "anchors_v4.md")
    c = load_layer(subject_dir, "core_v4.md")
    p = load_layer(subject_dir, "predictions_v4.md")
    parts = []
    if a: parts.append(f"=== ANCHORS ===\n{a}")
    if c: parts.append(f"=== CORE ===\n{c}")
    if p: parts.append(f"=== PREDICTIONS ===\n{p}")
    return "\n\n".join(parts)


def main():
    client = get_anthropic_client()

    # Load everything
    data = {}
    for name, path in SUBJECTS:
        data[name] = {
            "layers": format_layers(path),
            "c28": load_brief(path, "C28"),
            "c31": load_brief(path, "C31"),
        }

    prompt = DECISION_PROMPT.format(
        franklin_layers=data["franklin"]["layers"],
        c28_franklin=data["franklin"]["c28"],
        c31_franklin=data["franklin"]["c31"],
        buffett_layers=data["buffett"]["layers"],
        c28_buffett=data["buffett"]["c28"],
        c31_buffett=data["buffett"]["c31"],
        aarik_layers=data["aarik"]["layers"],
        c28_aarik=data["aarik"]["c28"],
        c31_aarik=data["aarik"]["c31"],
    )

    print(f"Prompt size: {len(prompt):,} chars")
    print("Sending to Collective (Opus)...")

    response = client.messages.create(
        model=OPUS,
        max_tokens=2000,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    cost = (response.usage.input_tokens * 15 + response.usage.output_tokens * 75) / 1_000_000
    print(f"Cost: ${cost:.3f}")
    print(f"\nRaw response:\n{text}")

    # Parse
    clean = text
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1]
        if clean.endswith("```"):
            clean = clean[:-3]
    try:
        decision = json.loads(clean)
        print(f"\n{'='*60}")
        print(f"  COLLECTIVE DECISION: {decision['winner']}")
        print(f"  Confidence: {decision['confidence']}")
        print(f"  Reasoning: {decision['reasoning']}")
        print(f"{'='*60}")
        print(f"  Franklin: {decision['franklin_preference']} — {decision['franklin_note']}")
        print(f"  Buffett:  {decision['buffett_preference']} — {decision['buffett_note']}")
        print(f"  Aarik:    {decision['aarik_preference']} — {decision['aarik_note']}")
        print(f"\n  Production: {decision['production_recommendation']}")
    except json.JSONDecodeError:
        print("(Could not parse JSON)")


if __name__ == "__main__":
    main()
