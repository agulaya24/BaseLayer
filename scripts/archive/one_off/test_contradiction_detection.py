"""
Contradiction Detection — Test Harness

Tests two layers of the contradiction detection pipeline:
1. SIMILARITY LAYER: Can MiniLM embeddings separate contradictory fact pairs
   from non-contradictory ones? What's the right similarity threshold?
2. JUDGMENT LAYER: Can an LLM correctly classify pairs as
   contradiction / enrichment / coexistent / ambiguous?

Uses hand-labeled test pairs derived from real facts in the database.
Results inform threshold selection and model choice (Qwen vs Sonnet vs Opus).

See: docs/reviews/TEMPORAL_PROCESSING_REVIEW.md (V3, Phase 2)
"""

import json
import sqlite3
import time
import sys

from config import DATABASE_FILE, VECTORS_DIR

# ---------------------------------------------------------------------------
# TEST PAIRS — hand-labeled from real database facts
# ---------------------------------------------------------------------------
# Each pair: (fact_A, fact_B, expected_label, cluster, notes)
# Labels: "contradiction", "enrichment", "coexistent", "unrelated"
#
# Contradictions: same entity + same attribute + different value
# Enrichments: same topic, new detail, no conflict
# Coexistent: same domain, genuinely both true
# Unrelated: semantically similar text, different dimensions

TEST_PAIRS = [
    # === CONTRADICTIONS (25) ===
    # Clear state changes — the classic case
    ("Alex wakes up at 5:30am for pre-market trading preparation",
     "Alex now wakes up around 7am",
     "contradiction", "how_you_operate",
     "Wake time changed — the original 5:30am bug"),

    ("Alex trades primarily SPY 0DTE options",
     "Alex has shifted to swing trading instead of day trading",
     "contradiction", "what_youve_built",
     "Trading strategy change"),

    ("Alex is building a startup called TechCo",
     "TechCo has been shut down",
     "contradiction", "what_youve_built",
     "Company state change — active vs shut down"),

    ("Alex lives in Austin, Texas",
     "Alex recently moved to San Francisco",
     "contradiction", "who_you_are",
     "Location change"),

    ("Alex works full-time at a tech company",
     "Alex is now fully self-employed as an independent trader",
     "contradiction", "who_you_are",
     "Employment status change"),

    ("Alex is skeptical about AI replacing human judgment",
     "Alex now believes AI will fundamentally replace most cognitive work",
     "contradiction", "what_you_believe",
     "Belief reversal"),

    # D-036: Owner labels this "coexistent" — fundraising and solo project are
    # not mutually exclusive without external context confirming TechCo was abandoned.
    # Do not change expected label yet; revisit in V2 test set.
    ("Alex's primary goal is to raise Series A funding for TechCo",
     "Alex is focused on building a personal AI memory system as a solo project",
     "contradiction", "where_youre_headed",
     "Goal shift — company fundraising vs solo project"),

    # D-036: Owner labels this "ambiguous" — scope mismatch between "journals
    # before market open" (trading journal) and "stopped journaling consistently"
    # (could be general journaling). Different journal types may be involved.
    # Do not change expected label yet; revisit in V2 test set.
    ("Alex journals every morning before market open",
     "Alex stopped journaling consistently months ago",
     "contradiction", "how_you_operate",
     "Habit cessation"),

    ("Alex uses Python exclusively for all coding projects",
     "Alex has switched to TypeScript for his main projects",
     "contradiction", "how_you_operate",
     "Tool preference change"),

    ("Alex runs 5 miles every morning",
     "Alex stopped running due to a knee injury",
     "contradiction", "how_you_operate",
     "Activity cessation"),

    ("Alex is reading 'Thinking, Fast and Slow' by Daniel Kahneman",
     "Alex finished 'Thinking, Fast and Slow' and moved on to 'Antifragile'",
     "contradiction", "how_you_operate",
     "Current activity state changed"),

    # D-036: Owner labels this "ambiguous/time-dependent" — account growth from
    # $50K to $120K could reflect natural growth over time, not a contradiction.
    # Without timestamps, this is indeterminate.
    # Do not change expected label yet; revisit in V2 test set.
    ("Alex's trading account is at $50K",
     "Alex's trading account has grown to $120K",
     "contradiction", "what_youve_built",
     "Quantitative state change"),

    # D-036: Owner labels this "enrichment" — a temporal update within a period.
    # Bearish-to-bullish within the same quarter is a view evolution, not a
    # contradiction requiring supersession.
    # Do not change expected label yet; revisit in V2 test set.
    ("Alex is bearish on the market for Q1 2026",
     "Alex turned bullish after January data",
     "contradiction", "what_you_believe",
     "Market view reversal"),

    ("Alex communicates primarily through Slack at work",
     "Alex no longer uses Slack since going independent",
     "contradiction", "how_you_operate",
     "Tool usage cessation from context change"),

    ("Alex is focused on options income as his primary revenue source",
     "Alex now considers consulting his primary revenue source",
     "contradiction", "where_youre_headed",
     "Primary income source change"),

    # D-036: Owner labels this "coexistent" — "sleeps 6 hours" is descriptive
    # reality while "prioritizes 8 hours" is aspirational intent. Both can be
    # simultaneously true (you can prioritize 8 hours and still only get 6).
    # Do not change expected label yet; revisit in V2 test set.
    ("Alex sleeps 6 hours per night",
     "Alex now prioritizes 8 hours of sleep",
     "contradiction", "how_you_operate",
     "Sleep habit change"),

    ("Alex avoids social media entirely",
     "Alex is actively posting on LinkedIn to build his professional brand",
     "contradiction", "how_you_operate",
     "Social media stance reversal"),

    ("Alex is mentoring two junior developers",
     "Alex stopped mentoring to focus entirely on his solo project",
     "contradiction", "what_youve_built",
     "Activity cessation"),

    ("Alex's cat Luna is healthy",
     "Luna has been diagnosed with kidney disease",
     "contradiction", "who_you_love",
     "Pet health state change"),

    ("Alex uses Claude as his primary AI assistant",
     "Alex switched to using GPT-4 as his primary AI tool",
     "contradiction", "how_you_operate",
     "Tool preference change"),

    ("Alex is planning to attend the AI conference in March",
     "Alex decided not to attend the March AI conference",
     "contradiction", "where_youre_headed",
     "Plan reversal"),

    ("Alex meditates daily using the Waking Up app",
     "Alex hasn't meditated in months",
     "contradiction", "how_you_operate",
     "Habit cessation"),

    ("Alex is applying for a fellowship at a research lab",
     "Alex withdrew his fellowship application to focus on shipping his product",
     "contradiction", "where_youre_headed",
     "Goal abandonment"),

    ("Alex primarily trades in the morning session before noon",
     "Alex now trades the afternoon session exclusively",
     "contradiction", "how_you_operate",
     "Routine time shift"),

    ("Alex has a weekly dinner with his parents every Sunday",
     "Alex's parents moved overseas so weekly dinners stopped",
     "contradiction", "who_you_love",
     "Relationship routine disrupted by context change"),

    # === ENRICHMENTS (10) ===
    # Same topic, additive detail, no conflict
    ("Alex trades SPY options",
     "Alex trades SPY and QQQ options with a focus on 0DTE contracts",
     "enrichment", "what_youve_built",
     "Expansion of trading scope — additive, not contradictory"),

    ("Alex is building a memory system",
     "Alex's memory system extracts facts using Qwen 2.5 14B locally",
     "enrichment", "what_youve_built",
     "Implementation detail added"),

    ("Alex exercises regularly",
     "Alex exercises 5 times per week, mostly strength training",
     "enrichment", "how_you_operate",
     "Degree specification — enriches, doesn't contradict"),

    ("Alex values privacy",
     "Alex built his AI system locally specifically to avoid sending personal data to cloud APIs",
     "enrichment", "what_you_believe",
     "Motivation detail behind a known value"),

    ("Alex has a cat",
     "Alex has a cat named Luna who is a calico",
     "enrichment", "who_you_love",
     "Name and detail added to existing fact"),

    ("Alex founded a startup",
     "Alex founded TechCo, which was accepted into an accelerator and raised seed funding",
     "enrichment", "what_youve_built",
     "Company details enriching bare fact"),

    ("Alex journals regularly",
     "Alex uses a structured format in his journal with sections for market analysis, personal reflection, and goals",
     "enrichment", "how_you_operate",
     "Method detail for known habit"),

    ("Alex is married",
     "Alex is married to Jordan",
     "enrichment", "who_you_love",
     "Spouse name added"),

    ("Alex trades options",
     "Alex uses a rules-based trading system with specific entry and exit criteria",
     "enrichment", "what_youve_built",
     "Methodology detail for known activity"),

    ("Alex is interested in AI",
     "Alex is specifically interested in personal AI systems that maintain memory across conversations",
     "enrichment", "what_youve_built",
     "Specification of interest area"),

    # === COEXISTENT (10) ===
    # Same domain, genuinely both true simultaneously
    ("Alex is building a memory system",
     "Alex is also trading options daily",
     "coexistent", "what_youve_built",
     "Two parallel activities — both true"),

    ("Alex loves his cat Luna",
     "Alex loves his wife Jordan",
     "coexistent", "who_you_love",
     "Multiple relationships — both true"),

    ("Alex believes in privacy for AI systems",
     "Alex believes AI will transform how people work",
     "coexistent", "what_you_believe",
     "Two compatible beliefs"),

    ("Alex struggles with overtrading when bored",
     "Alex struggles with perfectionism in his coding projects",
     "coexistent", "what_you_struggle_with",
     "Two independent struggles"),

    ("Alex wants to ship a public prototype in 90 days",
     "Alex wants to validate the memory system with Jordan's journal experiment",
     "coexistent", "where_youre_headed",
     "Two parallel goals"),

    ("Alex reads about cognitive science",
     "Alex reads about trading psychology",
     "coexistent", "how_you_operate",
     "Two reading interests"),

    ("Alex works on his memory system in the evening",
     "Alex trades during market hours in the morning",
     "coexistent", "how_you_operate",
     "Two activities at different times"),

    ("Alex's father influenced his interest in technology",
     "Alex's wife Jordan supports his entrepreneurial ambitions",
     "coexistent", "who_you_love",
     "Different family relationships"),

    ("Alex lost money on an impulsive NVDA trade",
     "Alex lost money on an SPY put that expired worthless",
     "coexistent", "what_youve_lost",
     "Two separate loss events"),

    ("Alex wants to apply for an AI fellowship",
     "Alex wants to build a multi-user version of his memory system",
     "coexistent", "where_youre_headed",
     "Two simultaneous goals"),

    # === UNRELATED (5) ===
    # Semantically similar text, but different dimensions entirely
    ("Alex values discipline in trading",
     "Alex values discipline in physical fitness",
     "unrelated", "what_drives_you",
     "Same trait, different domains — not contradictory or enriching"),

    ("Alex built TechCo with a team of 5 engineers",
     "Alex built his memory system entirely solo",
     "unrelated", "what_youve_built",
     "Different projects — not comparable"),

    ("Alex lost his startup TechCo",
     "Alex lost a significant amount on a single trade",
     "unrelated", "what_youve_lost",
     "Different types of loss — both true, not related"),

    ("Alex is writing code for the extraction pipeline",
     "Alex is writing a LinkedIn post about AI memory",
     "unrelated", "what_youve_built",
     "Same verb, different activities"),

    ("Alex prefers working alone on technical projects",
     "Alex prefers spending weekends with Jordan",
     "unrelated", "how_you_operate",
     "Same structure, completely different domains"),
]


def run_similarity_test():
    """
    Layer 1: Compute embedding similarity for all test pairs.
    Goal: Find threshold that separates contradictions from non-contradictions.
    """
    print("=" * 70)
    print("LAYER 1: EMBEDDING SIMILARITY TEST")
    print("=" * 70)

    from api_client import get_embedding_model
    import numpy as np

    print("\nLoading MiniLM model...")
    model = get_embedding_model()

    results_by_label = {"contradiction": [], "enrichment": [], "coexistent": [], "unrelated": []}

    print(f"\nComputing similarities for {len(TEST_PAIRS)} test pairs...\n")

    for fact_a, fact_b, label, cluster, notes in TEST_PAIRS:
        emb_a = model.encode([fact_a])[0]
        emb_b = model.encode([fact_b])[0]

        # Cosine similarity
        similarity = float(np.dot(emb_a, emb_b) / (np.linalg.norm(emb_a) * np.linalg.norm(emb_b)))
        results_by_label[label].append((similarity, fact_a[:60], fact_b[:60], notes))

    # Print results grouped by label
    for label in ["contradiction", "enrichment", "coexistent", "unrelated"]:
        entries = sorted(results_by_label[label], key=lambda x: x[0], reverse=True)
        print(f"\n--- {label.upper()} ({len(entries)} pairs) ---")
        sims = [e[0] for e in entries]
        print(f"  Mean: {sum(sims)/len(sims):.4f}  Min: {min(sims):.4f}  Max: {max(sims):.4f}")
        for sim, a, b, notes in entries:
            print(f"  {sim:.4f}  {a}...")
            print(f"          {b}...")
            print(f"          [{notes}]")

    # Distribution analysis
    print("\n" + "=" * 70)
    print("DISTRIBUTION ANALYSIS")
    print("=" * 70)

    contradiction_sims = [e[0] for e in results_by_label["contradiction"]]
    enrichment_sims = [e[0] for e in results_by_label["enrichment"]]
    coexistent_sims = [e[0] for e in results_by_label["coexistent"]]
    unrelated_sims = [e[0] for e in results_by_label["unrelated"]]
    non_contradiction_sims = enrichment_sims + coexistent_sims + unrelated_sims

    print(f"\nContradictions:     mean={sum(contradiction_sims)/len(contradiction_sims):.4f}  "
          f"range=[{min(contradiction_sims):.4f}, {max(contradiction_sims):.4f}]")
    print(f"Enrichments:        mean={sum(enrichment_sims)/len(enrichment_sims):.4f}  "
          f"range=[{min(enrichment_sims):.4f}, {max(enrichment_sims):.4f}]")
    print(f"Coexistent:         mean={sum(coexistent_sims)/len(coexistent_sims):.4f}  "
          f"range=[{min(coexistent_sims):.4f}, {max(coexistent_sims):.4f}]")
    print(f"Unrelated:          mean={sum(unrelated_sims)/len(unrelated_sims):.4f}  "
          f"range=[{min(unrelated_sims):.4f}, {max(unrelated_sims):.4f}]")

    # Key insight: contradictions and enrichments will BOTH have high similarity
    # (they're about the same topic). The embedding layer's job is to FILTER,
    # not to JUDGE. It surfaces candidates; the LLM judges.
    print(f"\n--- FILTER EFFECTIVENESS ---")
    print("The embedding layer filters candidates for LLM judgment.")
    print("High similarity = send to LLM. Low similarity = skip.")
    print("Contradictions AND enrichments should both pass the filter.")
    print("Unrelated pairs should be filtered out.\n")

    # Test various thresholds
    for threshold in [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85]:
        # "Positive" = would be sent to LLM (above threshold)
        contradiction_pass = sum(1 for s in contradiction_sims if s >= threshold)
        enrichment_pass = sum(1 for s in enrichment_sims if s >= threshold)
        coexistent_pass = sum(1 for s in coexistent_sims if s >= threshold)
        unrelated_pass = sum(1 for s in unrelated_sims if s >= threshold)

        # We want: contradictions pass, enrichments pass (LLM sorts them out),
        # unrelated filtered. Coexistent is gray zone.
        total_should_pass = len(contradiction_sims) + len(enrichment_sims)
        total_passed = contradiction_pass + enrichment_pass
        recall = total_passed / total_should_pass if total_should_pass else 0

        total_should_fail = len(unrelated_sims)
        total_failed = total_should_fail - unrelated_pass
        specificity = total_failed / total_should_fail if total_should_fail else 0

        print(f"  Threshold {threshold:.2f}: "
              f"Contradictions={contradiction_pass}/{len(contradiction_sims)}  "
              f"Enrichments={enrichment_pass}/{len(enrichment_sims)}  "
              f"Coexistent={coexistent_pass}/{len(coexistent_sims)}  "
              f"Unrelated={unrelated_pass}/{len(unrelated_sims)}  "
              f"Recall={recall:.0%}  Unrelated-filtered={specificity:.0%}")

    return results_by_label


def run_llm_judgment_test(model_name="qwen2.5:14b", use_api=False):
    """
    Layer 2: Test LLM judgment on fact pairs.
    Can the model correctly classify: contradiction / enrichment / coexistent / ambiguous?
    """
    print("\n" + "=" * 70)
    print(f"LAYER 2: LLM JUDGMENT TEST — {model_name}")
    print("=" * 70)

    import requests

    JUDGMENT_PROMPT = """You are evaluating whether two facts about the same person can coexist.

Fact A (older): {fact_a}
Fact B (newer): {fact_b}

Classify the relationship between these facts as exactly one of:
- "contradiction": Fact B makes Fact A no longer true. They cannot both be currently true.
- "enrichment": Fact B adds detail to Fact A. Both are true; B is more specific.
- "coexistent": Both facts are independently true. They describe different things.
- "ambiguous": Unclear whether they conflict. Needs human confirmation.

Return ONLY a JSON object:
{{"judgment": "<one of: contradiction, enrichment, coexistent, ambiguous>", "reasoning": "<one sentence>"}}"""

    correct = 0
    total = 0
    results = []
    errors = 0

    for fact_a, fact_b, expected, cluster, notes in TEST_PAIRS:
        prompt = JUDGMENT_PROMPT.format(fact_a=fact_a, fact_b=fact_b)

        try:
            if use_api:
                # ---------------------------------------------------------------
                # NOTE (D-033): The production architecture uses Claude Code
                # session execution for Sonnet/Opus judgment, NOT direct API
                # calls. This API path exists for standalone testing only.
                # See docs/core/DECISIONS.md, D-033.
                # ---------------------------------------------------------------
                from api_client import call_api
                response = call_api(
                    model=model_name,
                    max_tokens=200,
                    messages=[{"role": "user", "content": prompt}],
                    caller="test_contradiction_detection",
                )
                raw = response.content[0].text
            else:
                # Ollama path — for Qwen testing
                resp = requests.post(
                    "http://localhost:11434/api/generate",
                    json={
                        "model": model_name,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"num_predict": 200, "temperature": 0.1},
                    },
                    timeout=120,
                )
                raw = resp.json().get("response", "")

            # Parse JSON from response
            # Try to find JSON in the response
            try:
                # Direct parse
                parsed = json.loads(raw.strip())
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code block
                import re
                match = re.search(r'\{[^}]+\}', raw, re.DOTALL)
                if match:
                    parsed = json.loads(match.group())
                else:
                    parsed = {"judgment": "PARSE_ERROR", "reasoning": raw[:100]}

            judgment = parsed.get("judgment", "MISSING").lower().strip()

            # Map "unrelated" expected labels — LLM sees coexistent or ambiguous
            effective_expected = expected
            if expected == "unrelated":
                effective_expected = "coexistent"  # unrelated pairs should be classified as coexistent

            is_correct = judgment == effective_expected
            if is_correct:
                correct += 1
            total += 1

            status = "OK" if is_correct else "MISS"
            results.append({
                "fact_a": fact_a[:60],
                "fact_b": fact_b[:60],
                "expected": expected,
                "got": judgment,
                "correct": is_correct,
                "reasoning": parsed.get("reasoning", ""),
                "notes": notes,
            })

            print(f"  [{status}] expected={expected:15s} got={judgment:15s}  {notes}")

        except Exception as e:
            errors += 1
            total += 1
            print(f"  [ERR] {notes}: {e}")
            results.append({
                "fact_a": fact_a[:60],
                "fact_b": fact_b[:60],
                "expected": expected,
                "got": "ERROR",
                "correct": False,
                "reasoning": str(e),
                "notes": notes,
            })

    # Summary
    print(f"\n--- SUMMARY: {model_name} ---")
    print(f"  Accuracy: {correct}/{total} ({correct/total:.1%})" if total else "  No results")
    print(f"  Errors: {errors}")

    # Breakdown by expected label
    for label in ["contradiction", "enrichment", "coexistent", "unrelated"]:
        label_results = [r for r in results if r["expected"] == label]
        label_correct = sum(1 for r in label_results if r["correct"])
        if label_results:
            print(f"  {label:15s}: {label_correct}/{len(label_results)} ({label_correct/len(label_results):.0%})")

    # Show misses
    misses = [r for r in results if not r["correct"] and r["got"] != "ERROR"]
    if misses:
        print(f"\n  Misclassifications ({len(misses)}):")
        for r in misses:
            print(f"    expected={r['expected']:15s} got={r['got']:15s}  {r['notes']}")
            print(f"      Reasoning: {r['reasoning']}")

    return results


def run_iterative_refinement_test(model_name="qwen2.5:14b"):
    """
    Layer 2 variant B: Iterative refinement ("poor man's loop").
    Pass 1: Qwen judges the pair.
    Pass 2: Feed the pair + Qwen's own judgment back, ask it to reconsider.
    Tests whether self-correction catches value-replacement contradictions.

    Added Session 26 — inspired by Ouro/LoopLM research (arXiv 2510.25741).
    """
    print("\n" + "=" * 70)
    print(f"LAYER 2B: ITERATIVE REFINEMENT TEST — {model_name} (2-pass)")
    print("=" * 70)

    import requests

    JUDGMENT_PROMPT = """You are evaluating whether two facts about the same person can coexist.

Fact A (older): {fact_a}
Fact B (newer): {fact_b}

Classify the relationship between these facts as exactly one of:
- "contradiction": Fact B makes Fact A no longer true. They cannot both be currently true.
- "enrichment": Fact B adds detail to Fact A. Both are true; B is more specific.
- "coexistent": Both facts are independently true. They describe different things.
- "ambiguous": Unclear whether they conflict. Needs human confirmation.

Return ONLY a JSON object:
{{"judgment": "<one of: contradiction, enrichment, coexistent, ambiguous>", "reasoning": "<one sentence>"}}"""

    REFINEMENT_PROMPT = """You previously evaluated a fact pair and gave a judgment. Reconsider carefully.

Fact A (older): {fact_a}
Fact B (newer): {fact_b}

Your previous judgment: {prev_judgment}
Your previous reasoning: {prev_reasoning}

Reconsider: Does Fact B REPLACE or SUPERSEDE the state described in Fact A? If Fact A describes a current state (habit, location, activity, preference) and Fact B describes a different value for the same attribute, that is a contradiction even if Fact B doesn't explicitly negate Fact A.

Return ONLY a JSON object:
{{"judgment": "<one of: contradiction, enrichment, coexistent, ambiguous>", "reasoning": "<one sentence>", "changed": true/false}}"""

    correct = 0
    total = 0
    results = []
    errors = 0
    changed_count = 0
    changed_to_correct = 0

    for fact_a, fact_b, expected, cluster, notes in TEST_PAIRS:
        prompt_1 = JUDGMENT_PROMPT.format(fact_a=fact_a, fact_b=fact_b)

        try:
            # --- Pass 1: Initial judgment ---
            resp1 = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": model_name,
                    "prompt": prompt_1,
                    "stream": False,
                    "options": {"num_predict": 200, "temperature": 0.1},
                },
                timeout=120,
            )
            raw1 = resp1.json().get("response", "")

            import re
            try:
                parsed1 = json.loads(raw1.strip())
            except json.JSONDecodeError:
                match = re.search(r'\{[^}]+\}', raw1, re.DOTALL)
                parsed1 = json.loads(match.group()) if match else {"judgment": "PARSE_ERROR", "reasoning": raw1[:100]}

            judgment1 = parsed1.get("judgment", "MISSING").lower().strip()
            reasoning1 = parsed1.get("reasoning", "")

            # --- Pass 2: Refinement ---
            prompt_2 = REFINEMENT_PROMPT.format(
                fact_a=fact_a, fact_b=fact_b,
                prev_judgment=judgment1, prev_reasoning=reasoning1
            )
            resp2 = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": model_name,
                    "prompt": prompt_2,
                    "stream": False,
                    "options": {"num_predict": 200, "temperature": 0.1},
                },
                timeout=120,
            )
            raw2 = resp2.json().get("response", "")

            try:
                parsed2 = json.loads(raw2.strip())
            except json.JSONDecodeError:
                match = re.search(r'\{[^}]+\}', raw2, re.DOTALL)
                parsed2 = json.loads(match.group()) if match else {"judgment": judgment1, "reasoning": raw2[:100], "changed": False}

            judgment2 = parsed2.get("judgment", judgment1).lower().strip()
            did_change = judgment2 != judgment1

            if did_change:
                changed_count += 1

            # Map "unrelated" expected labels
            effective_expected = expected
            if expected == "unrelated":
                effective_expected = "coexistent"

            is_correct = judgment2 == effective_expected
            was_correct_before = judgment1 == effective_expected
            if is_correct:
                correct += 1
            if did_change and is_correct and not was_correct_before:
                changed_to_correct += 1
            total += 1

            status = "OK" if is_correct else "MISS"
            change_marker = " [CHANGED]" if did_change else ""
            results.append({
                "fact_a": fact_a[:60],
                "fact_b": fact_b[:60],
                "expected": expected,
                "pass1": judgment1,
                "pass2": judgment2,
                "changed": did_change,
                "correct": is_correct,
                "reasoning_1": reasoning1,
                "reasoning_2": parsed2.get("reasoning", ""),
                "notes": notes,
            })

            print(f"  [{status}] expected={expected:15s} p1={judgment1:15s} p2={judgment2:15s}{change_marker}  {notes}")

        except Exception as e:
            errors += 1
            total += 1
            print(f"  [ERR] {notes}: {e}")
            results.append({
                "fact_a": fact_a[:60],
                "fact_b": fact_b[:60],
                "expected": expected,
                "pass1": "ERROR",
                "pass2": "ERROR",
                "changed": False,
                "correct": False,
                "reasoning_1": str(e),
                "reasoning_2": "",
                "notes": notes,
            })

    # Summary
    print(f"\n--- SUMMARY: {model_name} (iterative refinement) ---")
    print(f"  Final accuracy: {correct}/{total} ({correct/total:.1%})" if total else "  No results")
    print(f"  Errors: {errors}")
    print(f"  Judgments changed on pass 2: {changed_count}")
    print(f"  Changed AND corrected (wrong->right): {changed_to_correct}")

    # Breakdown by expected label
    for label in ["contradiction", "enrichment", "coexistent", "unrelated"]:
        label_results = [r for r in results if r["expected"] == label]
        label_correct = sum(1 for r in label_results if r["correct"])
        if label_results:
            print(f"  {label:15s}: {label_correct}/{len(label_results)} ({label_correct/len(label_results):.0%})")

    # Show changes
    changes = [r for r in results if r["changed"]]
    if changes:
        print(f"\n  Pass 2 changes ({len(changes)}):")
        for r in changes:
            correction = "FIXED" if r["correct"] and r["pass1"] != r["pass2"] else "REGRESSED" if not r["correct"] else "LATERAL"
            print(f"    [{correction}] {r['pass1']:15s} → {r['pass2']:15s}  {r['notes']}")
            print(f"      P1: {r['reasoning_1']}")
            print(f"      P2: {r['reasoning_2']}")

    return results


def dump_pairs_for_session_judgment():
    """
    Output all test pairs as clean JSON for Opus judgment in a Claude Code session.
    No expected labels included — this is the clean blind test (fixes Session 23 contamination).

    Added Session 26.
    """
    print("\n" + "=" * 70)
    print("BLIND PAIR DUMP FOR OPUS SESSION JUDGMENT")
    print("No expected labels. No hints. Pure blind classification.")
    print("=" * 70)

    pairs = []
    for i, (fact_a, fact_b, expected, cluster, notes) in enumerate(TEST_PAIRS):
        pairs.append({
            "pair_id": i + 1,
            "fact_a": fact_a,
            "fact_b": fact_b,
            # expected label deliberately omitted — blind test
        })

    output_path = PROJECT_ROOT / "data" / "blind_test_pairs.json"
    with open(output_path, "w") as f:
        json.dump(pairs, f, indent=2)

    print(f"\n  Wrote {len(pairs)} pairs to {output_path}")
    print(f"  Labels stripped. Ready for blind session judgment.")
    return pairs


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--similarity-only" in args:
        run_similarity_test()
    elif "--qwen" in args:
        run_similarity_test()
        run_llm_judgment_test("qwen2.5:14b", use_api=False)
    elif "--qwen-iterative" in args:
        run_iterative_refinement_test("qwen2.5:14b")
    elif "--qwen-both" in args:
        run_similarity_test()
        run_llm_judgment_test("qwen2.5:14b", use_api=False)
        run_iterative_refinement_test("qwen2.5:14b")
    elif "--dump-blind" in args:
        dump_pairs_for_session_judgment()
    elif "--sonnet" in args:
        run_similarity_test()
        run_llm_judgment_test("claude-sonnet-4-5-20250929", use_api=True)
    elif "--opus" in args:
        run_similarity_test()
        run_llm_judgment_test("claude-opus-4-6", use_api=True)
    elif "--all-models" in args:
        run_similarity_test()
        run_llm_judgment_test("qwen2.5:14b", use_api=False)
        run_llm_judgment_test("claude-sonnet-4-5-20250929", use_api=True)
    else:
        print("Usage:")
        print("  python test_contradiction_detection.py --similarity-only")
        print("  python test_contradiction_detection.py --qwen              # Single-pass Qwen")
        print("  python test_contradiction_detection.py --qwen-iterative    # 2-pass Qwen (iterative refinement)")
        print("  python test_contradiction_detection.py --qwen-both         # Similarity + single-pass + iterative")
        print("  python test_contradiction_detection.py --dump-blind        # Export pairs for Opus session judgment")
        print("  python test_contradiction_detection.py --sonnet")
        print("  python test_contradiction_detection.py --opus")
        print("  python test_contradiction_detection.py --all-models")
        print()
        print("Start with --similarity-only to validate the embedding filter layer.")
        print("Then test LLM judgment with --qwen, --qwen-iterative, or --dump-blind for Opus.")
