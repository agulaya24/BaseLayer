"""
One-off script: Run Collective review on baselayer_meta v1 and v2 briefs.
Calls Opus directly with the COLLECTIVE_REVIEW_PROMPT adapted for unified briefs.
"""
import sys
import os
import json
import time

# Add scripts to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api_client import call_api
from config import LAYER_REVIEW_MODEL

from pathlib import Path
_HOME = Path.home() / "Anthropic"
BRIEF_V1_PATH = str(_HOME / "subjects" / "baselayer_meta_v1" / "data" / "identity_layers" / "brief_v4.md")
BRIEF_V2_PATH = str(_HOME / "subjects" / "baselayer_meta" / "data" / "identity_layers" / "brief_v4.md")

# Adapted from COLLECTIVE_REVIEW_PROMPT for unified briefs
REVIEW_PROMPT = """You are THE COLLECTIVE — four adversarial reviewers evaluating a unified identity brief for the Base Layer memory system. This brief will be injected into AI system prompts so the AI "knows" a project/system without being told.

CONTEXT: This brief was generated from Base Layer's own documentation — design decisions, architecture docs, progress logs, and design principles. It is a self-referential case study: the system modeling its own identity.

The subject uses they/them pronouns. The brief should NOT use gendered pronouns.

BRIEF TEXT:
---
{brief_text}
---

INPUT METADATA:
- Brief version: {version}
- Brief length: {char_count} characters
- Source: Base Layer project documentation (decisions, architecture, design principles, progress)
- Data density: {density_tier}
- Total active facts: {fact_count}

REVIEW AS FOUR PERSONAS. Each scores 0-100:

**Cognitive Scientist** — Is the behavioral architecture sound? Do the categories and patterns reflect genuine cognitive/behavioral distinctions of this system/project? Is there over-inference from thin data? Are the contradictions and tensions genuine or manufactured?

**Narrative Biographer** — Does this read as a coherent identity or a taxonomy? Is there narrative coherence? Are facts woven into meaning, or just listed? Does it capture the PROJECT's way of thinking vs just listing features?

**Epistemologist** — Are knowledge claims justified by the source documentation? Any over-confident assertions? Internal contradictions that aren't acknowledged? Are confidence levels appropriate given the source material?

**Pragmatic Engineer** — D-041 compliance (every sentence changes model behavior). Token efficiency. No deadweight sentences. Actionable directives, not observations. Would injecting this brief actually help an AI agent work on this project?

ADDITIONAL EVALUATION CRITERIA FOR SELF-REFERENTIAL BRIEF:
- Does the brief capture HOW the system thinks, not just WHAT it does?
- Are the design principles represented as behavioral patterns (not feature lists)?
- Would an AI agent reading this brief make better decisions about the project?
- Does it avoid self-referential paradoxes (describing itself describing itself)?
- Are failure modes and anti-patterns actionable?
- Pronoun check: Should use they/them throughout, NOT she/her or he/him.

For EACH issue found, provide a SPECIFIC fix instruction that can be fed back to the generation model. Do not say "improve X" — say exactly what to change and how.

Respond with ONLY valid JSON:
{{
  "scores": {{
    "cognitive_scientist": 0,
    "narrative_biographer": 0,
    "epistemologist": 0,
    "pragmatic_engineer": 0
  }},
  "combined": 0,
  "deploy": false,
  "issues": [
    {{
      "persona": "<which persona>",
      "category": "<d041_violation | redundancy | over_inference | narrative | format | hallucination | pronoun>",
      "description": "what is wrong",
      "fix": "specific regeneration instruction"
    }}
  ],
  "strengths": ["what is working well — preserve these in regeneration"],
  "summary": "2-3 sentence overall assessment"
}}"""


def review_brief(brief_path, version_label, fact_count):
    """Run Collective review on a single brief."""
    with open(brief_path, "r", encoding="utf-8") as f:
        brief_text = f.read()

    # Strip YAML frontmatter
    if brief_text.startswith("---"):
        end = brief_text.find("---", 3)
        if end != -1:
            brief_text = brief_text[end + 3:].strip()

    # Strip ## Injectable Block header
    brief_text = brief_text.replace("## Injectable Block\n\n", "").replace("## Injectable Block\n", "")

    char_count = len(brief_text)
    density_tier = "moderate" if fact_count < 500 else "dense"

    prompt = REVIEW_PROMPT.format(
        brief_text=brief_text,
        version=version_label,
        char_count=char_count,
        density_tier=density_tier,
        fact_count=fact_count,
    )

    print(f"\n{'='*60}")
    print(f"COLLECTIVE REVIEW: {version_label}")
    print(f"Brief: {brief_path}")
    print(f"Length: {char_count} chars | Facts: {fact_count} | Density: {density_tier}")
    print(f"{'='*60}")

    start = time.time()
    response = call_api(
        model=LAYER_REVIEW_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4096,
        temperature=0,
        caller="review_briefs",
    )
    elapsed = time.time() - start

    # Extract text and cost from Anthropic response object
    text = response.content[0].text
    usage = response.usage
    # Opus pricing: $15/M input, $75/M output
    cost = (usage.input_tokens * 15.0 + usage.output_tokens * 75.0) / 1_000_000

    # Parse JSON from response
    try:
        # Find JSON in response
        json_start = text.find("{")
        json_end = text.rfind("}") + 1
        result = json.loads(text[json_start:json_end])
    except (json.JSONDecodeError, ValueError) as e:
        print(f"ERROR parsing JSON: {e}")
        print(f"Raw response:\n{text}")
        return None

    # Print results
    scores = result.get("scores", {})
    combined = result.get("combined", 0)
    deploy = result.get("deploy", False)
    issues = result.get("issues", [])
    strengths = result.get("strengths", [])
    summary = result.get("summary", "")

    print(f"\nSCORES: {combined}/100 (CS:{scores.get('cognitive_scientist', '?')} "
          f"NB:{scores.get('narrative_biographer', '?')} "
          f"EP:{scores.get('epistemologist', '?')} "
          f"PE:{scores.get('pragmatic_engineer', '?')})")
    print(f"DEPLOY: {'YES' if deploy else 'NO'}")
    print(f"Cost: ${cost:.4f} | Time: {elapsed:.1f}s")

    print(f"\nSTRENGTHS:")
    for s in strengths:
        print(f"  + {s}")

    print(f"\nISSUES ({len(issues)}):")
    for issue in issues:
        print(f"  [{issue.get('persona', '?')}] [{issue.get('category', '?')}]")
        print(f"    {issue.get('description', '')}")
        print(f"    FIX: {issue.get('fix', '')}")
        print()

    print(f"SUMMARY: {summary}")

    return result


def main():
    print("Base Layer Self-Referential Brief — Collective Review")
    print("=" * 60)

    # V1: 96 facts
    v1_result = review_brief(BRIEF_V1_PATH, "v1 (96 facts, pre-cap-raise)", fact_count=96)

    # V2: 284 facts
    v2_result = review_brief(BRIEF_V2_PATH, "v2 (284 facts, post-cap-raise)", fact_count=284)

    # Comparison
    if v1_result and v2_result:
        print("\n" + "=" * 60)
        print("COMPARISON: v1 vs v2")
        print("=" * 60)
        v1_scores = v1_result.get("scores", {})
        v2_scores = v2_result.get("scores", {})
        v1_combined = v1_result.get("combined", 0)
        v2_combined = v2_result.get("combined", 0)

        print(f"\n{'Persona':<25} {'v1':>6} {'v2':>6} {'Delta':>8}")
        print("-" * 50)
        for persona in ["cognitive_scientist", "narrative_biographer", "epistemologist", "pragmatic_engineer"]:
            v1s = v1_scores.get(persona, 0)
            v2s = v2_scores.get(persona, 0)
            delta = v2s - v1s
            sign = "+" if delta > 0 else ""
            print(f"{persona:<25} {v1s:>6} {v2s:>6} {sign}{delta:>7}")
        print("-" * 50)
        print(f"{'COMBINED':<25} {v1_combined:>6} {v2_combined:>6} {'+' if v2_combined > v1_combined else ''}{v2_combined - v1_combined:>7}")
        print(f"\nv1 deploy: {v1_result.get('deploy', False)}")
        print(f"v2 deploy: {v2_result.get('deploy', False)}")


if __name__ == "__main__":
    main()
