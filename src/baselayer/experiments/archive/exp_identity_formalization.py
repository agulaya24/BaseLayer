"""
Experiment 6: Identity Formalization
======================================
Question: Can we define "identity" mathematically? What is identity, formally?

Method:
  - Use Qwen to generate and evaluate candidate identity definitions
  - Test 5 mathematical framings against real extracted facts
  - Score each framing on: completeness, falsifiability, operational usefulness

This experiment is more conceptual than the others — it uses the LLM as a reasoning
partner to explore formal definitions, then tests them against real pipeline output.

Candidate framings:
  1. Set-theoretic: Identity = set of (predicate, object) pairs with stability > threshold
  2. Information-theoretic: Identity = minimum description length of behavioral patterns
  3. Vector space: Identity = centroid of fact embeddings in high-dimensional space
  4. Graph-theoretic: Identity = core subgraph of fact co-occurrence network
  5. Dynamical systems: Identity = attractor states in behavioral trajectory space
"""

import json
import sys
import os
import time
import sqlite3
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.dirname(__file__))

from ollama_utils import call_qwen, call_qwen_chat, save_results

IDENTITY_FRAMINGS = {
    "set_theoretic": {
        "name": "Set-Theoretic Identity",
        "definition": "Identity I(S) = {(p, o) in Facts(S) : stability(p, o) >= tau}",
        "description": "Identity is the subset of extracted facts that are temporally stable. Two identities are similar iff their Jaccard similarity exceeds a threshold. Identity change = set difference over time.",
        "test_question": "Given a set of facts, can we define a stability threshold that separates identity-constitutive facts from transient ones? Is there a natural boundary?",
    },
    "information_theoretic": {
        "name": "Information-Theoretic Identity",
        "definition": "Identity I(S) = argmin_{B} |B| such that KL(P_behavior || P_brief) < epsilon",
        "description": "Identity is the minimum-length description (brief) that predicts behavioral patterns within epsilon of the full fact set. Compression ratio = |facts| / |brief tokens|. Better identity = higher compression with lower prediction loss.",
        "test_question": "Is there an optimal compression ratio beyond which prediction quality degrades? Our data shows 18:1 compression works. Is there a theoretical limit?",
    },
    "vector_space": {
        "name": "Vector Space Identity",
        "definition": "Identity I(S) = centroid(embed(facts_identity(S))) in R^d",
        "description": "Identity is a point in embedding space — the centroid of all identity-tier fact embeddings. Distance between identities = cosine distance between centroids. Identity change = centroid drift over time.",
        "test_question": "Does the centroid of identity facts meaningfully differ from the centroid of all facts? Is there a 'identity subspace' that can be projected onto?",
    },
    "graph_theoretic": {
        "name": "Graph-Theoretic Identity",
        "definition": "Identity I(S) = k-core(G_cooccurrence) where G = (predicates, co-occurrence edges)",
        "description": "Build a graph where nodes are predicates and edges connect predicates that co-occur in the same conversation. Identity = the densely connected core (k-core) of this graph. Peripheral predicates are context-dependent, not identity.",
        "test_question": "Do identity-tier predicates form a denser subgraph than non-identity predicates? What is the minimum k for a meaningful identity core?",
    },
    "dynamical_systems": {
        "name": "Dynamical Systems Identity",
        "definition": "Identity I(S) = {attractors A_i} of the behavioral trajectory T(S, t)",
        "description": "Track predicate frequencies over time as a trajectory in predicate-space. Identity = the attractor states this trajectory converges to. Multiple attractors = context-dependent identity modes. Basin of attraction = how strongly each mode pulls.",
        "test_question": "Do behavioral patterns converge to stable attractors, or do they drift continuously? Is 'identity' better modeled as fixed points or limit cycles?",
    },
}


def load_fact_statistics() -> dict:
    """Load real fact statistics from Franklin + User A for grounding."""
    stats = {}

    for subject, db_path in [
        ("franklin", str(Path(__file__).parent.parent.parent.parent / "subjects" / "franklin_memory" / "data" / "database" / "memory.db")),
        ("user_a", str(Path(__file__).parent.parent.parent / "data" / "database" / "memory.db")),
    ]:
        if not os.path.exists(db_path):
            continue
        conn = sqlite3.connect(db_path)

        total = conn.execute("SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL").fetchone()[0]
        preds = conn.execute(
            "SELECT predicate, COUNT(*) as cnt FROM memory_facts WHERE superseded_by IS NULL AND predicate IS NOT NULL GROUP BY predicate ORDER BY cnt DESC"
        ).fetchall()
        pred_dist = {r[0]: r[1] for r in preds}

        stats[subject] = {
            "total_facts": total,
            "unique_predicates": len(pred_dist),
            "top_predicates": dict(list(pred_dist.items())[:10]),
        }
        conn.close()

    return stats


def evaluate_framing(framing: dict, fact_stats: dict) -> dict:
    """Use Qwen to evaluate a mathematical framing of identity."""
    stats_summary = json.dumps(fact_stats, indent=2)

    prompt = f"""You are a mathematician and cognitive scientist evaluating formal definitions of personal identity.

PROPOSED DEFINITION:
  Name: {framing['name']}
  Formal: {framing['definition']}
  Description: {framing['description']}

REAL DATA (from an identity extraction pipeline):
{stats_summary}

EVALUATION CRITERIA:
1. COMPLETENESS (0-10): Does this definition capture what we intuitively mean by "identity"?
2. FALSIFIABILITY (0-10): Can this definition be empirically tested and potentially proven wrong?
3. OPERATIONALITY (0-10): Can this definition be computed from the data we have?
4. UNIQUENESS (0-10): Would this definition distinguish between different people?
5. STABILITY (0-10): Would this definition produce the same result on different samples of the same person's data?

TEST QUESTION: {framing['test_question']}

Respond with a JSON object:
{{
  "scores": {{"completeness": N, "falsifiability": N, "operationality": N, "uniqueness": N, "stability": N}},
  "total": N,
  "strengths": "...",
  "weaknesses": "...",
  "test_answer": "answer to the test question",
  "mathematical_refinement": "improved version of the formal definition",
  "implementation_sketch": "how to implement this with the pipeline's data"
}}"""

    try:
        response = call_qwen(prompt, max_tokens=3000, json_mode=True)
        return json.loads(response)
    except (json.JSONDecodeError, KeyError) as e:
        return {"error": str(e)}


def synthesize_identity_definition(evaluations: dict, fact_stats: dict) -> dict:
    """Ask Qwen to synthesize the best definition from all candidates."""
    eval_summary = ""
    for name, ev in evaluations.items():
        if "error" in ev:
            continue
        total = ev.get("total", sum(ev.get("scores", {}).values()))
        eval_summary += f"\n{name}: total={total}/50\n  Strengths: {ev.get('strengths', 'N/A')}\n  Weaknesses: {ev.get('weaknesses', 'N/A')}\n"

    prompt = f"""You evaluated 5 mathematical framings of personal identity. Here are the results:
{eval_summary}

Real pipeline data: {json.dumps(fact_stats, indent=2)}

Now SYNTHESIZE. Create a unified mathematical definition of identity that:
1. Combines the strongest elements of each framing
2. Is computable from structured facts (subject, predicate, object, confidence)
3. Distinguishes identity from personality from behavior
4. Defines when two briefs describe the "same identity"
5. Defines "identity change" formally

Respond with JSON:
{{
  "unified_definition": "formal mathematical definition",
  "components": ["list of component definitions"],
  "identity_vs_personality": "formal distinction",
  "identity_change": "formal definition of change",
  "similarity_metric": "how to compare two identities",
  "minimum_data": "minimum facts needed for identity to be defined",
  "open_questions": ["remaining questions this doesn't answer"],
  "key_insight": "the most important thing about identity this analysis revealed"
}}"""

    try:
        response = call_qwen(prompt, max_tokens=4000, json_mode=True)
        return json.loads(response)
    except (json.JSONDecodeError, KeyError) as e:
        return {"error": str(e)}


def main():
    print("=" * 60)
    print("EXPERIMENT 6: Identity Formalization")
    print("=" * 60)
    print("Can we define 'identity' mathematically?")
    print()

    fact_stats = load_fact_statistics()
    if fact_stats:
        for subj, s in fact_stats.items():
            print(f"  {subj}: {s['total_facts']} facts, {s['unique_predicates']} predicates")
    print()

    evaluations = {}
    for key, framing in IDENTITY_FRAMINGS.items():
        print(f"--- Evaluating: {framing['name']} ---")
        t0 = time.time()
        result = evaluate_framing(framing, fact_stats)
        elapsed = round(time.time() - t0, 1)

        if "error" not in result:
            scores = result.get("scores", {})
            total = sum(scores.values())
            result["total"] = total
            print(f"  Scores: C={scores.get('completeness',0)} F={scores.get('falsifiability',0)} "
                  f"O={scores.get('operationality',0)} U={scores.get('uniqueness',0)} "
                  f"S={scores.get('stability',0)} = {total}/50")
            print(f"  Strengths: {result.get('strengths', 'N/A')[:100]}")
        else:
            print(f"  ERROR: {result['error']}")

        result["time_seconds"] = elapsed
        evaluations[key] = result
        print()

    # Synthesis
    print("--- Synthesizing unified definition ---")
    synthesis = synthesize_identity_definition(evaluations, fact_stats)

    if "error" not in synthesis:
        print(f"\nUnified definition:\n  {synthesis.get('unified_definition', 'N/A')[:200]}")
        print(f"\nKey insight:\n  {synthesis.get('key_insight', 'N/A')[:200]}")
    print()

    # Rankings
    ranked = sorted(
        [(k, v) for k, v in evaluations.items() if "error" not in v],
        key=lambda x: x[1].get("total", 0),
        reverse=True,
    )

    summary = {
        "experiment": "identity_formalization",
        "question": "Can we define identity mathematically?",
        "framings_tested": len(IDENTITY_FRAMINGS),
        "rankings": [{"name": k, "total": v["total"]} for k, v in ranked],
        "best_framing": ranked[0][0] if ranked else None,
        "evaluations": evaluations,
        "synthesis": synthesis,
        "fact_statistics": fact_stats,
    }

    print("=" * 60)
    print("RANKINGS")
    for i, (name, ev) in enumerate(ranked):
        print(f"  {i+1}. {IDENTITY_FRAMINGS[name]['name']}: {ev['total']}/50")
    print("=" * 60)

    save_results("identity_formalization", summary)


if __name__ == "__main__":
    main()
