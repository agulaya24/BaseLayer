"""
Meta-review: The Collective evaluates Base Layer as a project, approach, and idea.
Uses the project's own review mechanism to reflect on itself.
"""
import sys
import os
import json
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api_client import call_api
from config import LAYER_REVIEW_MODEL

# Gather context files
from pathlib import Path
_HOME = Path.home() / "Anthropic"
_PROJECT = _HOME / "memory_system"
CONTEXT_FILES = {
    "PROJECT_OVERVIEW": str(_PROJECT / "docs" / "core" / "PROJECT_OVERVIEW.md"),
    "DESIGN_PRINCIPLES": str(_PROJECT / "docs" / "core" / "DESIGN_PRINCIPLES.md"),
    "BCB_FRAMEWORK": str(_PROJECT / "docs" / "eval" / "BCB_FRAMEWORK.md"),
    "STACKING_STUDY": str(_PROJECT / "docs" / "eval" / "STACKING_BENCHMARK_STUDY.md"),
    "AXIOM_BENCHMARK": str(_PROJECT / "docs" / "eval" / "AXIOM_BENCHMARK_SPEC.md"),
    "BRIEF_V1": str(_HOME / "subjects" / "baselayer_meta_v1" / "data" / "identity_layers" / "brief_v4.md"),
    "BRIEF_V2": str(_HOME / "subjects" / "baselayer_meta" / "data" / "identity_layers" / "brief_v4.md"),
}

REVIEW_PROMPT = """You are THE COLLECTIVE — four adversarial reviewers. But this time you are not reviewing a brief. You are reviewing the entire Base Layer project: its thesis, its approach, its methodology, its technical decisions, its evaluation strategy, and its readiness for the world.

Base Layer is a personal AI memory system built over 76 sessions by a non-technical architect (the developer) working with Claude (Opus/Sonnet). It extracts behavioral patterns from text (conversations, journals, patents, letters, autobiographies), compresses them into a portable identity brief (~3,500 tokens), and injects that brief into AI conversations so the AI "knows" you without being told every time.

Below is the full project documentation. Read it carefully before reviewing.

=== PROJECT OVERVIEW ===
{project_overview}

=== DESIGN PRINCIPLES (first 200 lines — core philosophical commitments) ===
{design_principles}

=== BEHAVIORAL COMPRESSION BENCHMARK (BCB-0.1) ===
{bcb_framework}

=== STACKING BENCHMARK STUDY ===
{stacking_study}

=== AXIOM-CONDITIONED DOMAIN REASONING BENCHMARK (ADRB) ===
{axiom_benchmark}

=== SELF-REFERENTIAL BRIEFS ===
The system was run on its own documentation as a case study. Two versions were generated:

--- V1 BRIEF (96 facts from first extraction) ---
{brief_v1}

--- V2 BRIEF (284 facts after extraction cap fix) ---
{brief_v2}

=== KEY RESULTS ===
- N=10 subjects validated (personal conversations, newsletters, journals, autobiographies, patents, investor letters/memos)
- All subjects scored 73-82/100 on Collective review
- Franklin eval: C5c (brief) outperformed C2 (full structured data) by +0.40 — compression AMPLIFIED signal
- the developer eval: C5c retained 96.6% of full-context lift (SRS = 96.6%) despite 99.98% token reduction
- 14-step pipeline, 25 CLI subcommands, 47 predicates, 72 logged decisions, 414 tests
- Total build cost: ~$500 in API calls across 76 sessions
- Pipeline cost per subject: ~$0.50-3.00
- Built by one non-technical person + Claude over ~3 months

=== WORKING PROCESS ===
- the developer does not write code. He architects, directs, and evaluates.
- Every architectural decision is logged (72 decisions, each with reasoning, alternatives considered, and status)
- Claude (Opus for architecture/judgment, Sonnet for generation/execution) implements all code
- The process itself is iterative: design principle → implementation → empirical validation → revision
- The system has never been publicly released. Website is live at base-layer.ai with 7 case studies.
- Launch target: HN Show HN post

=== COMPETITIVE CONTEXT ===
- Mem0: $24M raised, YC-backed, API-first memory system. Stores and retrieves facts.
- Supermemory: SOTA on LongMemEval_s (81.6%). Atomic memories + temporal metadata + hybrid search. $2.6M seed.
- ChatGPT Memory: Built into ChatGPT, stores flat facts from conversations.
- Claude Memory: Categorized facts, recently added import feature.
- Zep: Enterprise memory for agents. Knowledge graph approach.
- Letta (formerly MemGPT): Self-editing memory with inner/outer thought.

Base Layer's positioning: NOT a replacement for memory systems. An identity LAYER that sits on top. "Memory remembers what you said. Base Layer understands who you are."

---

REVIEW AS FOUR PERSONAS. Each evaluates the full project holistically — the idea, the execution, the approach, the evaluation strategy, the competitive positioning, the readiness for launch, and the working process itself.

**Research Scientist** — Evaluate the intellectual rigor. Are the design principles philosophically sound? Is the evaluation methodology valid? Are the claims pre-registered and falsifiable? Where is the reasoning strongest and weakest? Is the BCB framework a genuine contribution or benchmark-washing? Does the ADRB hypothesis hold up? Would this survive peer review?

**Product Strategist** — Evaluate the market positioning. Is "identity layer" a real category or a distinction without a difference? Can a solo builder compete with $24M+ funded teams? Is the stacking thesis defensible or will memory providers just add compression? What's the moat? Is the pricing viable? Is the "non-replacement" positioning strength or weakness? Would YOU use this? Would you invest in this?

**Systems Architect** — Evaluate the technical approach. Is a 14-step pipeline overengineered or appropriately complex? Is the model role separation (Haiku extraction, Sonnet generation, Opus review) sound? Are the quality gates real or theatrical? Is the decision to use LLMs for classification/tiering vs. traditional ML justified? What are the scaling bottlenecks? Is the provenance system genuine or decorative? Is building this with Claude Code sustainable?

**Cognitive Psychologist** — Evaluate the identity modeling approach. Is "behavioral compression" a valid concept or a compelling metaphor? Do the three layers (ANCHORS, CORE, PREDICTIONS) map to real cognitive structures? Is the Inherent Incompleteness principle genuine humility or an excuse for limitations? Does the system actually model behavior or just organize facts? Can ~3,500 tokens genuinely capture "who someone is"? What does the self-referential case study reveal about the system's strengths and blind spots?

Also evaluate THE WORKING PROCESS: A non-technical person building a sophisticated AI pipeline entirely through conversation with Claude. What does this say about the future of software development? About the relationship between architectural thinking and implementation? Is 76 sessions of iterative development with AI a strength (deep refinement) or a weakness (echo chamber)?

For each persona, provide:
1. Score (0-100)
2. What's genuinely impressive
3. What's genuinely concerning
4. One thing that would change your assessment dramatically (up or down)

Respond with ONLY valid JSON:
{{
  "scores": {{
    "research_scientist": 0,
    "product_strategist": 0,
    "systems_architect": 0,
    "cognitive_psychologist": 0
  }},
  "combined": 0,
  "personas": {{
    "research_scientist": {{
      "impressive": ["..."],
      "concerning": ["..."],
      "swing_factor": "..."
    }},
    "product_strategist": {{
      "impressive": ["..."],
      "concerning": ["..."],
      "swing_factor": "..."
    }},
    "systems_architect": {{
      "impressive": ["..."],
      "concerning": ["..."],
      "swing_factor": "..."
    }},
    "cognitive_psychologist": {{
      "impressive": ["..."],
      "concerning": ["..."],
      "swing_factor": "..."
    }}
  }},
  "working_process_assessment": {{
    "what_it_reveals": "...",
    "strengths": ["..."],
    "risks": ["..."]
  }},
  "overall_verdict": "3-5 sentence honest assessment of Base Layer as a project, an idea, and an approach. What is it really? Is it ready? Does it matter?",
  "hardest_question": "The single hardest question the team needs to answer before launch."
}}"""


def load_file(path, max_chars=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        if max_chars and len(text) > max_chars:
            text = text[:max_chars] + "\n\n[TRUNCATED]"
        return text
    except Exception as e:
        return f"[ERROR reading {path}: {e}]"


def main():
    print("=" * 70)
    print("THE COLLECTIVE — Meta-Review of Base Layer")
    print("=" * 70)
    print()

    # Load all context
    context = {}
    total_chars = 0
    for key, path in CONTEXT_FILES.items():
        # Truncate design principles to avoid token explosion
        max_chars = 15000 if key == "DESIGN_PRINCIPLES" else None
        max_chars = 8000 if key == "AXIOM_BENCHMARK" else max_chars
        text = load_file(path, max_chars=max_chars)
        context[key] = text
        total_chars += len(text)
        print(f"  Loaded {key}: {len(text):,} chars")

    print(f"\n  Total context: {total_chars:,} chars (~{total_chars // 4:,} tokens)")

    prompt = REVIEW_PROMPT.format(
        project_overview=context["PROJECT_OVERVIEW"],
        design_principles=context["DESIGN_PRINCIPLES"],
        bcb_framework=context["BCB_FRAMEWORK"],
        stacking_study=context["STACKING_STUDY"],
        axiom_benchmark=context["AXIOM_BENCHMARK"],
        brief_v1=context["BRIEF_V1"],
        brief_v2=context["BRIEF_V2"],
    )

    print(f"\n  Final prompt: {len(prompt):,} chars (~{len(prompt) // 4:,} tokens)")
    print(f"  Model: {LAYER_REVIEW_MODEL}")
    print(f"  Estimated cost: ~$0.40-0.80")
    print()
    print("Sending to Opus...")
    print()

    start = time.time()
    response = call_api(
        model=LAYER_REVIEW_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=8192,
        temperature=0,
        caller="review_project_meta",
    )
    elapsed = time.time() - start

    text = response.content[0].text
    usage = response.usage
    cost = (usage.input_tokens * 15.0 + usage.output_tokens * 75.0) / 1_000_000

    print(f"Response received in {elapsed:.1f}s")
    print(f"Tokens: {usage.input_tokens:,} in / {usage.output_tokens:,} out")
    print(f"Cost: ${cost:.4f}")
    print()

    # Parse JSON
    try:
        json_start = text.find("{")
        json_end = text.rfind("}") + 1
        result = json.loads(text[json_start:json_end])
    except (json.JSONDecodeError, ValueError) as e:
        print(f"JSON parse error: {e}")
        print(f"\nRaw response:\n{text}")
        return

    # Display results
    scores = result.get("scores", {})
    combined = result.get("combined", 0)
    personas = result.get("personas", {})

    print("=" * 70)
    print(f"COMBINED SCORE: {combined}/100")
    print("=" * 70)

    for persona_key, persona_label in [
        ("research_scientist", "RESEARCH SCIENTIST"),
        ("product_strategist", "PRODUCT STRATEGIST"),
        ("systems_architect", "SYSTEMS ARCHITECT"),
        ("cognitive_psychologist", "COGNITIVE PSYCHOLOGIST"),
    ]:
        score = scores.get(persona_key, "?")
        data = personas.get(persona_key, {})
        print(f"\n{'-' * 70}")
        print(f"{persona_label}: {score}/100")
        print(f"{'-' * 70}")

        print("\n  IMPRESSIVE:")
        for item in data.get("impressive", []):
            print(f"    + {item}")

        print("\n  CONCERNING:")
        for item in data.get("concerning", []):
            print(f"    - {item}")

        swing = data.get("swing_factor", "")
        if swing:
            print(f"\n  SWING FACTOR: {swing}")

    # Working process
    wp = result.get("working_process_assessment", {})
    if wp:
        print(f"\n{'=' * 70}")
        print("WORKING PROCESS ASSESSMENT")
        print(f"{'=' * 70}")
        reveals = wp.get("what_it_reveals", "")
        if reveals:
            print(f"\n  {reveals}")
        print("\n  STRENGTHS:")
        for s in wp.get("strengths", []):
            print(f"    + {s}")
        print("\n  RISKS:")
        for r in wp.get("risks", []):
            print(f"    - {r}")

    # Overall verdict
    verdict = result.get("overall_verdict", "")
    if verdict:
        print(f"\n{'=' * 70}")
        print("OVERALL VERDICT")
        print(f"{'=' * 70}")
        print(f"\n  {verdict}")

    # Hardest question
    hq = result.get("hardest_question", "")
    if hq:
        print(f"\n{'=' * 70}")
        print("HARDEST QUESTION")
        print(f"{'=' * 70}")
        print(f"\n  {hq}")

    print()

    # Save full result
    out_path = str(_PROJECT / "docs" / "reviews" / "META_REVIEW_COLLECTIVE.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"Full results saved to: {out_path}")


if __name__ == "__main__":
    main()
