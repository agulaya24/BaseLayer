"""
Cross-Provider LLM Evaluation Script (D-052)

Runs the same pipeline prompts through multiple LLM providers and saves
outputs side-by-side for blind comparison. Supports extraction, classification,
tiering, and authoring steps.

Usage:
    # Compare extraction across 3 models, sampling 10 conversations
    python eval_cross_provider.py --step extraction \\
        --models claude-haiku-4-5-20251001,gpt-4o-mini,gemini-2.0-flash \\
        --sample 10

    # Compare authoring across models for the CORE layer
    python eval_cross_provider.py --step authoring \\
        --models claude-sonnet-4-20250514,gpt-4o,gemini-2.0-pro \\
        --layer core

    # Compare classification on 20 random facts
    python eval_cross_provider.py --step classification \\
        --models claude-haiku-4-5-20251001,gpt-4o-mini \\
        --sample 20

    # Compare tiering on 15 random facts
    python eval_cross_provider.py --step tiering \\
        --models claude-sonnet-4-20250514,gpt-4o \\
        --sample 15

    # List available runs
    python eval_cross_provider.py --list

Output: JSON files saved to data/eval/cross_provider/ with full metadata
and per-model results for blind comparison.
"""

import argparse
import contextlib
import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure scripts dir is importable
sys.path.insert(0, os.path.dirname(__file__))

from config import (
    DATABASE_FILE, PROJECT_ROOT,
    VALID_FACT_TYPES, VALID_COMMITMENT_DEPTHS,
    get_db,
)
from llm_provider import call_llm, detect_provider, get_provider_info, estimate_cost


# ---------------------------------------------------------------------------
# Output directory
# ---------------------------------------------------------------------------

EVAL_DIR = PROJECT_ROOT / "data" / "eval" / "cross_provider"


def ensure_eval_dir():
    """Create the eval output directory if it doesn't exist."""
    EVAL_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _generate_run_id(step: str) -> str:
    """Generate a unique run ID from step name and timestamp."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{step}_{ts}"


def _save_results(run_id: str, results: dict):
    """Save eval results to a JSON file."""
    ensure_eval_dir()
    filepath = EVAL_DIR / f"{run_id}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nResults saved to: {filepath}")
    return filepath


def _validate_models(models: list[str]) -> list[dict]:
    """Check that each model is detectable and its provider is available.
    Returns list of provider info dicts. Prints warnings but doesn't abort."""
    infos = []
    for model in models:
        try:
            info = get_provider_info(model=model)
            if not info["package_installed"]:
                print(f"  WARNING: {model} requires package for {info['provider']} "
                      f"but it is not installed.")
            if not info["api_key_set"]:
                env_vars = " or ".join(info["api_key_env_vars"])
                print(f"  WARNING: {model} requires {env_vars} but it is not set.")
            infos.append(info)
        except ValueError as e:
            print(f"  ERROR: {e}")
            sys.exit(1)
    return infos


def _call_model_safe(prompt: str, model: str, max_tokens: int = 4096,
                     temperature: float = 0) -> dict:
    """Call a model with error handling. Returns result dict or error dict."""
    start = time.time()
    try:
        result = call_llm(prompt, model=model, max_tokens=max_tokens,
                          temperature=temperature)
        elapsed = time.time() - start
        cost = estimate_cost(model, result["input_tokens"], result["output_tokens"])
        return {
            "status": "success",
            "text": result["text"],
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
            "model": model,
            "provider": detect_provider(model),
            "elapsed_seconds": round(elapsed, 2),
            "estimated_cost_usd": round(cost, 6),
        }
    except Exception as e:
        elapsed = time.time() - start
        return {
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__,
            "model": model,
            "provider": detect_provider(model) if model else "unknown",
            "elapsed_seconds": round(elapsed, 2),
        }


# ---------------------------------------------------------------------------
# Step: EXTRACTION
# ---------------------------------------------------------------------------

def _get_extraction_prompt(conv_title: str, conv_text: str) -> str:
    """Build the extraction prompt (mirrors extract_facts.py)."""
    return f"""You are extracting personal facts about a user from their conversation with an AI assistant.

Conversation title: "{conv_title}"

{conv_text}

Extract facts about the USER. For each fact, identify:
- WHO the fact is about (the user, or someone else like their wife, friend, colleague)
- WHAT the user's relationship is to this fact (does this, is learning about, asked about, used to do)
- Whether this is CURRENT or PAST
- Whether this is an EVENT or STATE:
  - EVENT: Something that happened. A one-time occurrence, milestone, or biographical anchor. Events are immutable.
  - STATE: Something currently true about the person. A mutable condition that could change over time.
- Knowledge tier:
  - IDENTITY: Who this person IS. Biographical anchors, values, behavioral patterns, durable preferences, proven skills. Stable over months/years.
  - SITUATIONAL: Current mutable conditions true NOW, persisting weeks/months. Active projects, employment.
  - CONTEXT: One-off conversation artifacts. Product lookups, specific task details, debugging sessions.

Focus on: Biography, Preferences, Projects, Relationships, Interests, Skills, Values, Habits, Opinions, Goals, Negative traits, Reasoning patterns, Emotional triggers, Interaction preferences, Foundational beliefs
Do NOT extract trivial conversation artifacts unless they reveal something durable about the person.

Respond with ONLY valid JSON matching this schema. No explanation, no markdown fences.
Schema: {{"facts": [{{"fact": "string", "category": "string", "subject": "string", "intent": "string", "temporal": "string", "fact_class": "string", "knowledge_tier": "string", "confidence": 0.0}}]}}

Return a JSON object with a "facts" array."""


def _sample_conversations(n: int) -> list[dict]:
    """Randomly sample N conversations with messages from the database."""
    with contextlib.closing(get_db()) as conn:
        # Get conversations that have been extracted (have messages and enough content)
        rows = conn.execute("""
            SELECT c.id, c.title, c.source, COUNT(m.id) as msg_count
            FROM conversations c
            JOIN messages m ON m.conversation_id = c.id
            WHERE c.title IS NOT NULL
            AND LENGTH(c.title) > 3
            GROUP BY c.id
            HAVING msg_count >= 6
            ORDER BY RANDOM()
            LIMIT ?
        """, (n,)).fetchall()

        conversations = []
        for row in rows:
            conv_id, title, source, msg_count = row
            messages = conn.execute("""
                SELECT role, content FROM messages
                WHERE conversation_id = ?
                ORDER BY sequence_number
            """, (conv_id,)).fetchall()

            # Build conversation text (same truncation as extract_facts.py)
            conv_text = ""
            msg_list = []
            for msg in messages:
                role = msg["role"].capitalize() if msg["role"] else "User"
                text = (msg["content"] or "")[:1500]
                msg_list.append({"role": role, "text": text})
                conv_text += f"{role}: {text}\n"
                if len(conv_text) > 12000:
                    conv_text += "\n[conversation continues...]\n"
                    break

            conversations.append({
                "id": conv_id,
                "title": title,
                "source": source,
                "message_count": msg_count,
                "conv_text": conv_text,
            })

        return conversations


def run_extraction_eval(models: list[str], sample_size: int):
    """Run extraction through multiple models on the same conversations."""
    print(f"\n=== EXTRACTION EVAL ===")
    print(f"Models: {', '.join(models)}")
    print(f"Sample size: {sample_size}")

    # Validate models
    _validate_models(models)

    # Sample conversations
    print(f"\nSampling {sample_size} conversations from database...")
    conversations = _sample_conversations(sample_size)
    if not conversations:
        print("ERROR: No eligible conversations found in database.")
        return
    print(f"  Got {len(conversations)} conversations")

    run_id = _generate_run_id("extraction")
    results = {
        "run_id": run_id,
        "step": "extraction",
        "models": models,
        "sample_size": len(conversations),
        "timestamp": datetime.now().isoformat(),
        "conversations": [],
        "summary": {},
    }

    total_costs = {m: 0.0 for m in models}
    total_facts = {m: 0 for m in models}
    total_errors = {m: 0 for m in models}

    for i, conv in enumerate(conversations, 1):
        print(f"\n[{i}/{len(conversations)}] \"{conv['title'][:60]}\" ({conv['message_count']} msgs)")

        prompt = _get_extraction_prompt(conv["title"], conv["conv_text"])

        conv_result = {
            "conversation_id": conv["id"],
            "title": conv["title"],
            "source": conv["source"],
            "message_count": conv["message_count"],
            "model_outputs": {},
        }

        for model in models:
            print(f"  {model}...", end=" ", flush=True)
            output = _call_model_safe(prompt, model, max_tokens=2000, temperature=0.1)

            if output["status"] == "success":
                # Try to parse the JSON to count facts
                text = output["text"]
                # Strip markdown fences if present
                if text.startswith("```"):
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]
                    text = text.strip()

                try:
                    parsed = json.loads(text)
                    fact_count = len(parsed.get("facts", []))
                    output["parsed_fact_count"] = fact_count
                    output["parse_success"] = True
                    total_facts[model] += fact_count
                    print(f"{fact_count} facts ({output['elapsed_seconds']}s, ${output['estimated_cost_usd']:.4f})")
                except json.JSONDecodeError:
                    output["parsed_fact_count"] = 0
                    output["parse_success"] = False
                    total_errors[model] += 1
                    print(f"JSON parse error ({output['elapsed_seconds']}s)")

                total_costs[model] += output.get("estimated_cost_usd", 0)
            else:
                total_errors[model] += 1
                print(f"ERROR: {output.get('error', 'unknown')[:80]}")

            conv_result["model_outputs"][model] = output

        results["conversations"].append(conv_result)

    # Summary
    results["summary"] = {
        model: {
            "total_facts_extracted": total_facts[model],
            "avg_facts_per_conversation": round(total_facts[model] / len(conversations), 1) if conversations else 0,
            "total_errors": total_errors[model],
            "total_cost_usd": round(total_costs[model], 4),
        }
        for model in models
    }

    print(f"\n=== SUMMARY ===")
    for model in models:
        s = results["summary"][model]
        print(f"  {model}: {s['total_facts_extracted']} facts "
              f"(avg {s['avg_facts_per_conversation']}/conv), "
              f"{s['total_errors']} errors, ${s['total_cost_usd']:.4f}")

    _save_results(run_id, results)


# ---------------------------------------------------------------------------
# Step: CLASSIFICATION
# ---------------------------------------------------------------------------

def _get_classification_prompt(facts: list[tuple]) -> str:
    """Build the classification prompt (mirrors classify_facts_haiku.py)."""
    lines = []
    for fid, text in facts:
        clean = text.replace('"', "'").replace("\n", " ").replace("\r", " ")[:200]
        lines.append(f'[{fid}] {clean}')
    fact_list = "\n".join(lines)

    return f"""Classify each fact about a person.

**fact_type** (what kind of knowledge):
biographical -- facts about who they are, what happened to them, relationships, job history, one-off actions
behavioral -- RECURRING patterns of how they characteristically act, react, or operate
positional -- what they explicitly believe, argue for, or evaluate as true/important
preference -- what they like, are interested in, choose, or gravitate toward

**Disambiguation rules (apply these BEFORE classifying):**
- "Interested in X" -> **preference** if it's a stable/general interest. But if it describes a one-time task, that's **biographical**.
- "Considering X" / "planning to X" -> **biographical** (an action), NOT behavioral or positional
- "Skilled at X" -> **biographical** (a capability), NOT behavioral
- Personality traits -> **biographical**, NOT behavioral
- behavioral requires a RECURRING pattern, not a one-time action
- positional requires an evaluative STANCE, not just interest

**commitment_depth** (how strongly held):
factual -- not a belief; events, identifiers, relationships, observed capabilities
preference -- soft, could change easily
position -- argued for, but would revise with evidence
conviction -- core to who they are, would not change without fundamental shift

**Disambiguation rules:**
- Observed skills/competencies -> **factual**, not conviction
- Observed behavioral patterns -> **factual**, not position
- conviction requires deep identification, not just competence

Return JSON array: [{{"id": "...", "fact_type": "...", "commitment_depth": "..."}}]

Facts:
{fact_list}"""


def _sample_facts(n: int) -> list[tuple]:
    """Randomly sample N active personal-scope facts from the database."""
    with contextlib.closing(get_db()) as conn:
        rows = conn.execute("""
            SELECT id, fact_text FROM memory_facts
            WHERE superseded_by IS NULL
            AND scope = 'personal'
            ORDER BY RANDOM()
            LIMIT ?
        """, (n,)).fetchall()
        return [(row["id"], row["fact_text"]) for row in rows]


def run_classification_eval(models: list[str], sample_size: int):
    """Run classification through multiple models on the same facts."""
    print(f"\n=== CLASSIFICATION EVAL ===")
    print(f"Models: {', '.join(models)}")
    print(f"Sample size: {sample_size}")

    _validate_models(models)

    print(f"\nSampling {sample_size} facts from database...")
    facts = _sample_facts(sample_size)
    if not facts:
        print("ERROR: No eligible facts found in database.")
        return
    print(f"  Got {len(facts)} facts")

    prompt = _get_classification_prompt(facts)

    run_id = _generate_run_id("classification")
    results = {
        "run_id": run_id,
        "step": "classification",
        "models": models,
        "sample_size": len(facts),
        "timestamp": datetime.now().isoformat(),
        "facts": [{"id": fid, "text": text} for fid, text in facts],
        "model_outputs": {},
        "summary": {},
    }

    for model in models:
        print(f"\n  {model}...", end=" ", flush=True)
        output = _call_model_safe(prompt, model, max_tokens=8192, temperature=0)

        if output["status"] == "success":
            text = output["text"]
            # Extract JSON array
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                text = text[start:end]

            try:
                parsed = json.loads(text)
                output["parsed_classifications"] = parsed
                output["parse_success"] = True
                output["classified_count"] = len(parsed)
                print(f"{len(parsed)} classified ({output['elapsed_seconds']}s, "
                      f"${output['estimated_cost_usd']:.4f})")
            except json.JSONDecodeError:
                output["parse_success"] = False
                output["classified_count"] = 0
                print(f"JSON parse error ({output['elapsed_seconds']}s)")
        else:
            print(f"ERROR: {output.get('error', 'unknown')[:80]}")

        results["model_outputs"][model] = output

    # Agreement analysis: for each fact, check if models agree
    _analyze_classification_agreement(results, models, facts)

    _save_results(run_id, results)


def _analyze_classification_agreement(results: dict, models: list[str], facts: list[tuple]):
    """Analyze inter-model agreement on classifications."""
    # Build a lookup: fact_id -> model -> classification
    classifications = {}  # fact_id -> {model: {fact_type, commitment_depth}}
    for model in models:
        output = results["model_outputs"].get(model, {})
        parsed = output.get("parsed_classifications", [])
        for item in parsed:
            fid = str(item.get("id", ""))
            if fid not in classifications:
                classifications[fid] = {}
            classifications[fid][model] = {
                "fact_type": item.get("fact_type", ""),
                "commitment_depth": item.get("commitment_depth", ""),
            }

    # Count agreement
    total_compared = 0
    ft_agree = 0
    cd_agree = 0
    both_agree = 0

    for fid, model_results in classifications.items():
        if len(model_results) < 2:
            continue

        model_list = list(model_results.keys())
        # Compare all pairs
        for i in range(len(model_list)):
            for j in range(i + 1, len(model_list)):
                m1, m2 = model_list[i], model_list[j]
                r1, r2 = model_results[m1], model_results[m2]
                total_compared += 1
                ft_match = r1["fact_type"] == r2["fact_type"]
                cd_match = r1["commitment_depth"] == r2["commitment_depth"]
                if ft_match:
                    ft_agree += 1
                if cd_match:
                    cd_agree += 1
                if ft_match and cd_match:
                    both_agree += 1

    if total_compared > 0:
        results["summary"]["agreement"] = {
            "pairs_compared": total_compared,
            "fact_type_agreement": round(ft_agree / total_compared * 100, 1),
            "commitment_depth_agreement": round(cd_agree / total_compared * 100, 1),
            "both_agreement": round(both_agree / total_compared * 100, 1),
        }
        a = results["summary"]["agreement"]
        print(f"\n  Agreement ({a['pairs_compared']} pairs): "
              f"fact_type {a['fact_type_agreement']}%, "
              f"commitment_depth {a['commitment_depth_agreement']}%, "
              f"both {a['both_agreement']}%")
    else:
        results["summary"]["agreement"] = {"pairs_compared": 0, "note": "insufficient data"}


# ---------------------------------------------------------------------------
# Step: TIERING
# ---------------------------------------------------------------------------

def _get_tiering_prompt(facts: list[tuple]) -> str:
    """Build the tiering prompt (mirrors reclassify_tiers.py)."""
    fact_lines = []
    for i, (fid, text, cat) in enumerate(facts, 1):
        fact_lines.append(f"{i}. [{cat or 'unknown'}] {text}")

    return f"""You are classifying facts about a person into knowledge tiers for a memory system.

CRITICAL RULES:
1. If the fact is about someone OTHER than the primary user, classify as context.
2. Apply the "single conversation test": would this fact make sense to someone who never saw the conversation it came from? If NOT, it is context.
3. "The user was doing X in a conversation" is NOT the same as "the user is the kind of person who does X." Doing something once is context. Doing something as a pattern is identity.
4. When in doubt between situational and context, choose context.
5. When in doubt between identity and situational, choose situational.

**IDENTITY** -- Who this person IS. Biographical anchors, relationships, values, behavioral patterns, durable preferences, proven skills, formative experiences. Would appear in a 500-word biography. Stable over months/years.

**SITUATIONAL** -- Current mutable conditions true NOW, persisting weeks/months. Active projects, ongoing dispositions, living situation, employment.

**CONTEXT** -- Conversation artifacts. One-off tasks, specific lookups, single-conversation activities, third-party observations, specific trade setups, product research.

For each fact below, respond with ONLY a JSON array of tier classifications in order.
Example response: ["context", "identity", "situational", "context", "identity"]

Facts to classify:
{chr(10).join(fact_lines)}"""


def _sample_facts_for_tiering(n: int) -> list[tuple]:
    """Sample N facts with their categories for tiering eval."""
    with contextlib.closing(get_db()) as conn:
        rows = conn.execute("""
            SELECT id, fact_text, category FROM memory_facts
            WHERE superseded_by IS NULL
            AND scope = 'personal'
            AND subject = 'user'
            ORDER BY RANDOM()
            LIMIT ?
        """, (n,)).fetchall()
        return [(row["id"], row["fact_text"], row["category"]) for row in rows]


def run_tiering_eval(models: list[str], sample_size: int):
    """Run tiering through multiple models on the same facts."""
    print(f"\n=== TIERING EVAL ===")
    print(f"Models: {', '.join(models)}")
    print(f"Sample size: {sample_size}")

    _validate_models(models)

    print(f"\nSampling {sample_size} facts from database...")
    facts = _sample_facts_for_tiering(sample_size)
    if not facts:
        print("ERROR: No eligible facts found in database.")
        return
    print(f"  Got {len(facts)} facts")

    prompt = _get_tiering_prompt(facts)

    run_id = _generate_run_id("tiering")
    results = {
        "run_id": run_id,
        "step": "tiering",
        "models": models,
        "sample_size": len(facts),
        "timestamp": datetime.now().isoformat(),
        "facts": [{"id": fid, "text": text, "category": cat} for fid, text, cat in facts],
        "model_outputs": {},
        "summary": {},
    }

    valid_tiers = {"identity", "situational", "context"}

    for model in models:
        print(f"\n  {model}...", end=" ", flush=True)
        output = _call_model_safe(prompt, model, max_tokens=500, temperature=0)

        if output["status"] == "success":
            text = output["text"]
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                text = text[start:end]

            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    # Normalize and validate
                    tiers = [t.strip().lower() if isinstance(t, str) else "" for t in parsed]
                    valid = [t for t in tiers if t in valid_tiers]
                    output["parsed_tiers"] = tiers
                    output["parse_success"] = True
                    output["valid_count"] = len(valid)
                    output["expected_count"] = len(facts)

                    # Distribution
                    dist = {}
                    for t in tiers:
                        dist[t] = dist.get(t, 0) + 1
                    output["distribution"] = dist

                    print(f"{len(valid)}/{len(facts)} valid ({output['elapsed_seconds']}s, "
                          f"${output['estimated_cost_usd']:.4f}) — {dist}")
                else:
                    output["parse_success"] = False
                    print(f"Expected array, got {type(parsed).__name__}")
            except json.JSONDecodeError:
                output["parse_success"] = False
                print(f"JSON parse error ({output['elapsed_seconds']}s)")
        else:
            print(f"ERROR: {output.get('error', 'unknown')[:80]}")

        results["model_outputs"][model] = output

    # Agreement analysis
    _analyze_tiering_agreement(results, models, facts)

    _save_results(run_id, results)


def _analyze_tiering_agreement(results: dict, models: list[str], facts: list[tuple]):
    """Analyze inter-model agreement on tier classifications."""
    # Build per-fact tier arrays
    model_tiers = {}
    for model in models:
        output = results["model_outputs"].get(model, {})
        tiers = output.get("parsed_tiers", [])
        model_tiers[model] = tiers

    total_compared = 0
    agree = 0

    for idx in range(len(facts)):
        tier_values = []
        for model in models:
            tiers = model_tiers.get(model, [])
            if idx < len(tiers):
                tier_values.append(tiers[idx])

        if len(tier_values) >= 2:
            # Compare all pairs
            for i in range(len(tier_values)):
                for j in range(i + 1, len(tier_values)):
                    total_compared += 1
                    if tier_values[i] == tier_values[j]:
                        agree += 1

    if total_compared > 0:
        pct = round(agree / total_compared * 100, 1)
        results["summary"]["agreement"] = {
            "pairs_compared": total_compared,
            "tier_agreement_pct": pct,
        }
        print(f"\n  Agreement ({total_compared} pairs): {pct}%")
    else:
        results["summary"]["agreement"] = {"pairs_compared": 0, "note": "insufficient data"}


# ---------------------------------------------------------------------------
# Step: AUTHORING
# ---------------------------------------------------------------------------

def _get_authoring_input(layer: str) -> dict:
    """Retrieve facts and build the authoring prompt for a given layer.
    Returns {"prompt": str, "fact_count": int, "facts_summary": str} or None."""
    # Import author_layers functions for fact retrieval
    from author_layers import (
        retrieve_anchors_facts,
        retrieve_core_facts,
        retrieve_predictions_facts,
        format_facts_for_prompt,
        ANCHORS_PROMPT,
        CORE_PROMPT,
        PREDICTIONS_PROMPT,
    )

    with contextlib.closing(get_db()) as conn:
        if layer == "anchors":
            data = retrieve_anchors_facts(conn)
            if data["count"] == 0:
                return None

            if data["source"] == "epistemic_anchors_table":
                lines = []
                for a in data["anchors"]:
                    lines.append(f"Axiom {a['number']}: {a['text']}")
                    if a.get("formulation"):
                        lines.append(f"  Formulation: {a['formulation']}")
                facts_text = "\n".join(lines)
            else:
                facts_text = format_facts_for_prompt(data["facts"])

            prompt = ANCHORS_PROMPT.replace("{facts}", facts_text)
            return {"prompt": prompt, "fact_count": data["count"],
                    "facts_summary": f"{data['count']} anchor facts from {data['source']}"}

        elif layer == "core":
            data = retrieve_core_facts(conn)
            if data["count"] == 0:
                return None

            by_type = data["facts_by_type"]
            prompt = CORE_PROMPT.replace(
                "{biographical}", format_facts_for_prompt(by_type.get("biographical", []))
            ).replace(
                "{behavioral}", format_facts_for_prompt(by_type.get("behavioral", []))
            ).replace(
                "{positional}", format_facts_for_prompt(by_type.get("positional", []))
            ).replace(
                "{preference}", format_facts_for_prompt(by_type.get("preference", []))
            )
            return {"prompt": prompt, "fact_count": data["count"],
                    "facts_summary": f"{data['count']} core facts by type"}

        elif layer == "predictions":
            data = retrieve_predictions_facts(conn)
            if data["count"] == 0:
                return None

            facts_text = format_facts_for_prompt(data["facts"])
            prompt = PREDICTIONS_PROMPT.replace("{facts}", facts_text)
            return {"prompt": prompt, "fact_count": data["count"],
                    "facts_summary": f"{data['count']} prediction facts"}

        else:
            print(f"ERROR: Unknown layer '{layer}'. Use: anchors, core, predictions")
            return None


def run_authoring_eval(models: list[str], layer: str):
    """Run layer authoring through multiple models with the same input facts."""
    print(f"\n=== AUTHORING EVAL ({layer.upper()} layer) ===")
    print(f"Models: {', '.join(models)}")

    _validate_models(models)

    print(f"\nRetrieving {layer} facts from database...")
    authoring_input = _get_authoring_input(layer)
    if authoring_input is None:
        print(f"ERROR: No facts found for {layer} layer.")
        return
    print(f"  {authoring_input['facts_summary']}")

    run_id = _generate_run_id(f"authoring_{layer}")
    results = {
        "run_id": run_id,
        "step": "authoring",
        "layer": layer,
        "models": models,
        "fact_count": authoring_input["fact_count"],
        "facts_summary": authoring_input["facts_summary"],
        "timestamp": datetime.now().isoformat(),
        "model_outputs": {},
        "summary": {},
    }

    # Note: we do NOT save the full prompt to avoid leaking personal facts
    # into eval results. We save the fact count and summary only.

    for model in models:
        print(f"\n  {model}...", end=" ", flush=True)
        output = _call_model_safe(authoring_input["prompt"], model,
                                  max_tokens=4096, temperature=0)

        if output["status"] == "success":
            word_count = len(output["text"].split())
            char_count = len(output["text"])
            output["word_count"] = word_count
            output["char_count"] = char_count
            output["approx_tokens"] = char_count // 4
            print(f"{word_count} words ({output['elapsed_seconds']}s, "
                  f"${output['estimated_cost_usd']:.4f})")
        else:
            print(f"ERROR: {output.get('error', 'unknown')[:80]}")

        results["model_outputs"][model] = output

    # Summary
    for model in models:
        o = results["model_outputs"].get(model, {})
        results["summary"][model] = {
            "status": o.get("status"),
            "word_count": o.get("word_count", 0),
            "approx_tokens": o.get("approx_tokens", 0),
            "elapsed_seconds": o.get("elapsed_seconds", 0),
            "estimated_cost_usd": o.get("estimated_cost_usd", 0),
        }

    print(f"\n=== SUMMARY ===")
    for model in models:
        s = results["summary"][model]
        print(f"  {model}: {s['word_count']} words, "
              f"~{s['approx_tokens']} tokens, "
              f"{s['elapsed_seconds']}s, ${s['estimated_cost_usd']:.4f}")

    filepath = _save_results(run_id, results)

    # Also save individual layer outputs as separate text files for easy reading
    for model in models:
        o = results["model_outputs"].get(model, {})
        if o.get("status") == "success":
            safe_name = model.replace("/", "_").replace(":", "_")
            text_path = EVAL_DIR / f"{run_id}_{safe_name}.txt"
            with open(text_path, "w", encoding="utf-8") as f:
                f.write(f"# {layer.upper()} Layer — {model}\n")
                f.write(f"# Generated: {results['timestamp']}\n")
                f.write(f"# Facts: {authoring_input['fact_count']}\n")
                f.write(f"# Words: {o.get('word_count', 0)}\n")
                f.write(f"---\n\n")
                f.write(o["text"])
            print(f"  Layer text saved: {text_path}")


# ---------------------------------------------------------------------------
# List runs
# ---------------------------------------------------------------------------

def list_runs():
    """List all eval runs in the output directory."""
    if not EVAL_DIR.exists():
        print("No eval runs found (directory does not exist).")
        return

    json_files = sorted(EVAL_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not json_files:
        print("No eval runs found.")
        return

    print(f"\nCross-provider eval runs ({len(json_files)}):\n")
    print(f"{'Run ID':<40} {'Step':<16} {'Models':<50} {'Date':<20}")
    print("-" * 126)

    for f in json_files:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            run_id = data.get("run_id", f.stem)
            step = data.get("step", "?")
            layer = data.get("layer", "")
            if layer:
                step = f"{step}/{layer}"
            models = ", ".join(data.get("models", []))
            ts = data.get("timestamp", "?")[:19]
            print(f"{run_id:<40} {step:<16} {models:<50} {ts:<20}")
        except (json.JSONDecodeError, KeyError):
            print(f"{f.stem:<40} {'(corrupt)':<16}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Cross-provider LLM evaluation for Base Layer pipeline steps",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python eval_cross_provider.py --step extraction --models claude-haiku-4-5-20251001,gpt-4o-mini --sample 10
  python eval_cross_provider.py --step classification --models claude-haiku-4-5-20251001,gpt-4o-mini --sample 20
  python eval_cross_provider.py --step tiering --models claude-sonnet-4-20250514,gpt-4o --sample 15
  python eval_cross_provider.py --step authoring --models claude-sonnet-4-20250514,gpt-4o --layer core
  python eval_cross_provider.py --list
""",
    )
    parser.add_argument("--step", choices=["extraction", "classification", "tiering", "authoring"],
                        help="Pipeline step to evaluate")
    parser.add_argument("--models", type=str,
                        help="Comma-separated list of model names to compare")
    parser.add_argument("--sample", type=int, default=10,
                        help="Number of items to sample (default: 10)")
    parser.add_argument("--layer", choices=["anchors", "core", "predictions"],
                        default="core",
                        help="Layer to author (only for --step authoring, default: core)")
    parser.add_argument("--list", action="store_true",
                        help="List all previous eval runs")
    args = parser.parse_args()

    if args.list:
        list_runs()
        return

    if not args.step:
        parser.error("--step is required (or use --list)")

    if not args.models:
        parser.error("--models is required (comma-separated model names)")

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    if len(models) < 1:
        parser.error("Must specify at least one model")

    if args.step == "extraction":
        run_extraction_eval(models, args.sample)
    elif args.step == "classification":
        run_classification_eval(models, args.sample)
    elif args.step == "tiering":
        run_tiering_eval(models, args.sample)
    elif args.step == "authoring":
        run_authoring_eval(models, args.layer)


if __name__ == "__main__":
    main()
