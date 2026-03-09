"""
A/B/C Blind Evaluation Runner — Brief vs. Raw History vs. Baseline

Generates responses for 10 eval prompts under three conditions:
  A: Baseline — no context (cold-start LLM)
  B: Raw History — semantically retrieved conversation excerpts (~2,600 tokens)
  C: Brief — assembled brief (identity + theme + episodes)

Same model, same temperature, same prompt. Responses are randomized to X/Y/Z
labels and saved for blind rating by the subject.

Run: python run_eval.py --generate              # Generate all A/B/C responses
     python run_eval.py --generate --prompt 3    # Generate for prompt #3 only
     python run_eval.py --rate                    # Interactive blind rating
     python run_eval.py --reveal                  # Unblind and show results
     python run_eval.py --summary                 # Show score summary
"""

import contextlib
import sys
import io
import sqlite3
import json
import time
import random
import argparse
import os
from pathlib import Path
from datetime import datetime

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from config import (
    DATABASE_FILE, VECTORS_DIR, EMBEDDING_MODEL,
    CHARS_PER_TOKEN, TOTAL_TOKEN_BUDGET,
    MESSAGES_COLLECTION_NAME,
)

# Reuse brief assembly from assemble_brief.py
from assemble_brief import (
    assemble_brief, get_db_connection, create_tables,
    get_current_identity, estimate_tokens,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EVAL_DIR = Path(__file__).parent.parent / "data" / "eval"
EVAL_MODEL = "claude-sonnet-4-5-20250929"
EVAL_TEMPERATURE = 0  # Deterministic for reproducibility
EVAL_MAX_TOKENS = 2048
RAW_HISTORY_TOKEN_BUDGET = 2600  # Match brief total budget for fair comparison

# ---------------------------------------------------------------------------
# Eval Prompts (Session 32, Collective-reviewed)
# ---------------------------------------------------------------------------

EVAL_PROMPTS = [
    {
        "id": 1,
        "category": "emotional",
        "prompt": "I just had my worst trading day in months. Broke my rules, revenge traded, and lost $400.",
        "clusters": ["struggle", "operate"],
    },
    {
        "id": 2,
        "category": "career/life",
        "prompt": "I got an offer for a VP of Operations role at a growth-stage company, but it means pausing my main project. How should I think about this?",
        "clusters": ["built", "lost", "drives", "headed"],
    },
    {
        "id": 3,
        "category": "preference",
        "prompt": "My partner and I are planning our anniversary dinner. What kind of place should we look for?",
        "clusters": ["love", "operate"],
    },
    {
        "id": 4,
        "category": "practical",
        "prompt": "How should I pitch my project to someone who's never heard of it?",
        "clusters": ["built", "believe", "headed"],
    },
    {
        "id": 5,
        "category": "preference/life",
        "prompt": "I'm considering getting another cat. Good idea?",
        "clusters": ["love", "who_you_are"],
    },
    {
        "id": 6,
        "category": "emotional/reflection",
        "prompt": "Sometimes I wonder if I'm just building another thing that won't make it, like my last startup. How do I know this is different?",
        "clusters": ["lost", "drives", "headed"],
    },
    {
        "id": 7,
        "category": "practical",
        "prompt": "I need to make a decision about whether to build the multi-user auth system myself or use a third-party service like Auth0. Walk me through how to think about this.",
        "clusters": ["operate", "believe"],
    },
    {
        "id": 8,
        "category": "lifestyle/advice",
        "prompt": "My back has been killing me lately and I've been skipping the gym. How do I get back on track?",
        "clusters": ["struggle", "operate"],
    },
    {
        "id": 9,
        "category": "career/debate",
        "prompt": "A VC just told me that fine-tuning is the future of AI personalization and memory systems like mine are a dead end. How do I respond?",
        "clusters": ["believe", "built", "headed"],
    },
    {
        "id": 10,
        "category": "creative",
        "prompt": "Help me write the opening paragraph of a blog post about why AI should remember you.",
        "clusters": ["believe", "operate"],
    },
]

DIMENSIONS = [
    "personalization_accuracy",
    "behavioral_prediction",
    "advice_fit",
    "tone_match",
    "novel_composition",
    "seen_factor",
]

DIMENSION_LABELS = {
    "personalization_accuracy": "Personalization Accuracy",
    "behavioral_prediction": "Behavioral Prediction",
    "advice_fit": "Advice Fit",
    "tone_match": "Tone Match",
    "novel_composition": "Novel Composition",
    "seen_factor": "\"Seen\" Factor",
}


# ---------------------------------------------------------------------------
# Model + Embedding Setup
# ---------------------------------------------------------------------------

def get_embed_model():
    """Load sentence transformer model (centralized singleton from api_client)."""
    from api_client import get_embedding_model
    model = get_embedding_model()
    if model is None:
        raise ImportError("Could not load embedding model. Run: pip install sentence-transformers")
    return model


def get_chroma_client():
    """Get ChromaDB client."""
    import chromadb
    return chromadb.PersistentClient(path=str(VECTORS_DIR))


def get_anthropic_client():
    """Get Anthropic API client with retry and timeout (delegates to api_client)."""
    from api_client import get_anthropic_client as _get_client
    return _get_client()


# ---------------------------------------------------------------------------
# Condition B: Raw History Retrieval
# ---------------------------------------------------------------------------

def retrieve_raw_history(user_message, embed_model, chroma_client, token_budget=None):
    """
    Retrieve raw conversation excerpts semantically similar to the prompt.

    This simulates what platform memory (ChatGPT, Claude) does:
    retrieve unstructured conversation snippets, no extraction or synthesis.
    """
    if token_budget is None:
        token_budget = RAW_HISTORY_TOKEN_BUDGET

    char_budget = token_budget * CHARS_PER_TOKEN

    # Embed the user message
    embedding = embed_model.encode([user_message]).tolist()

    # Query the messages collection (raw conversation turns)
    try:
        messages_collection = chroma_client.get_collection(MESSAGES_COLLECTION_NAME)
        results = messages_collection.query(
            query_embeddings=embedding,
            n_results=50,  # Get plenty, then trim to budget
        )
    except Exception as e:
        print(f"  WARNING: Messages collection query failed: {e}")
        return ""

    if not results or not results["documents"] or not results["documents"][0]:
        return ""

    docs = results["documents"][0]
    metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(docs)
    distances = results["distances"][0] if results.get("distances") else [0] * len(docs)

    # Build raw history context: conversation excerpts with minimal formatting
    lines = []
    total_chars = 0

    for doc, meta, dist in zip(docs, metas, distances):
        role = meta.get("role", "unknown")
        title = meta.get("conversation_title", "")
        created_at = meta.get("created_at", 0)

        # Format as a raw excerpt (simulating platform memory)
        if created_at:
            try:
                date_str = datetime.fromtimestamp(float(created_at)).strftime("%Y-%m-%d")
            except (ValueError, OSError):
                date_str = ""
        else:
            date_str = ""

        # Trim very long messages
        excerpt = doc[:500] if len(doc) > 500 else doc

        header = f"[{role}"
        if date_str:
            header += f", {date_str}"
        if title:
            header += f", \"{title[:50]}\""
        header += "]"

        entry = f"{header}\n{excerpt}\n"

        if total_chars + len(entry) > char_budget:
            break

        lines.append(entry)
        total_chars += len(entry)

    raw_text = "\n".join(lines).strip()
    return raw_text


def format_raw_history_prompt(raw_history):
    """Format raw history as a system prompt for condition B."""
    if not raw_history:
        return ""

    return f"""The following are excerpts from previous conversations with this user. Use them to personalize your response, but do not recite them verbatim.

<conversation_history>
{raw_history}
</conversation_history>"""


# ---------------------------------------------------------------------------
# Response Generation
# ---------------------------------------------------------------------------

def generate_response(client, system_prompt, user_message):
    """Generate a Claude response with the given system prompt."""
    messages = [{"role": "user", "content": user_message}]

    kwargs = {
        "model": EVAL_MODEL,
        "max_tokens": EVAL_MAX_TOKENS,
        "temperature": EVAL_TEMPERATURE,
        "messages": messages,
    }

    if system_prompt:
        kwargs["system"] = system_prompt

    try:
        response = client.messages.create(**kwargs)
        return response.content[0].text
    except Exception as e:
        print(f"  ERROR: API call failed: {e}")
        return f"[ERROR: {e}]"


def generate_all_conditions(prompt_data, client, conn, embed_model, chroma_client):
    """Generate A/B/C responses for a single prompt."""
    prompt_text = prompt_data["prompt"]
    prompt_id = prompt_data["id"]

    print(f"\n  Prompt #{prompt_id}: {prompt_text[:60]}...")

    # Condition A: Baseline (no context)
    print(f"    Generating condition A (baseline)...")
    response_a = generate_response(client, None, prompt_text)

    # Condition B: Raw History
    print(f"    Generating condition B (raw history)...")
    raw_history = retrieve_raw_history(prompt_text, embed_model, chroma_client)
    system_b = format_raw_history_prompt(raw_history)
    response_b = generate_response(client, system_b, prompt_text)

    # Condition C: Brief
    print(f"    Generating condition C (brief)...")
    brief_xml, metadata = assemble_brief(conn, prompt_text, embed_model, chroma_client)
    response_c = generate_response(client, brief_xml, prompt_text)

    # Randomize labels
    conditions = [
        {"condition": "A", "label": None, "response": response_a,
         "system_tokens": 0},
        {"condition": "B", "label": None, "response": response_b,
         "system_tokens": estimate_tokens(system_b)},
        {"condition": "C", "label": None, "response": response_c,
         "system_tokens": metadata["total_tokens"]},
    ]

    # Shuffle and assign X/Y/Z labels
    random.shuffle(conditions)
    labels = ["X", "Y", "Z"]
    for i, cond in enumerate(conditions):
        cond["label"] = labels[i]

    print(f"    Done. Labels: {', '.join(c['label'] + '=' + c['condition'] for c in conditions)}")

    return {
        "prompt_id": prompt_id,
        "prompt_text": prompt_text,
        "category": prompt_data["category"],
        "conditions": conditions,
        "generated_at": datetime.now().isoformat(),
        "model": EVAL_MODEL,
        "temperature": EVAL_TEMPERATURE,
        # Store the mapping separately (for reveal)
        "label_map": {c["label"]: c["condition"] for c in conditions},
    }


# ---------------------------------------------------------------------------
# Generation Mode
# ---------------------------------------------------------------------------

def run_generate(prompt_id=None):
    """Generate A/B/C responses for all (or one) eval prompts."""
    EVAL_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Eval Runner — Generating A/B/C Responses")
    print("=" * 60)

    # Setup
    print("\nInitializing...")
    client = get_anthropic_client()
    embed_model = get_embed_model()
    chroma_client = get_chroma_client()

    with contextlib.closing(get_db_connection()) as conn:
        create_tables(conn)

        identity = get_current_identity(conn)
        if not identity:
            print("WARNING: No identity block found. Condition C will have empty identity.")

        # Select prompts
        if prompt_id:
            prompts = [p for p in EVAL_PROMPTS if p["id"] == prompt_id]
            if not prompts:
                print(f"ERROR: No prompt with id={prompt_id}")
                return
        else:
            prompts = EVAL_PROMPTS

        print(f"\nGenerating responses for {len(prompts)} prompt(s)...")

        # Load existing results (to allow incremental generation)
        results_file = EVAL_DIR / "eval_results.json"
        if results_file.exists():
            with open(results_file, "r", encoding="utf-8") as f:
                all_results = json.load(f)
        else:
            all_results = {}

        start = time.time()

        for prompt_data in prompts:
            pid = str(prompt_data["id"])

            # Skip if already generated (unless regenerating a specific prompt)
            if pid in all_results and not prompt_id:
                print(f"\n  Prompt #{pid}: already generated, skipping (use --prompt {pid} to regenerate)")
                continue

            result = generate_all_conditions(prompt_data, client, conn, embed_model, chroma_client)
            all_results[pid] = result

            # Save after each prompt (in case of interruption)
            with open(results_file, "w", encoding="utf-8") as f:
                json.dump(all_results, f, indent=2, ensure_ascii=False)

        elapsed = time.time() - start

    print(f"\n{'=' * 60}")
    print(f"Generation complete in {elapsed:.1f}s")
    print(f"Results saved to: {results_file}")
    print(f"\nNext step: python run_eval.py --rate")

    # Also generate the blind rating file
    _generate_rating_file(all_results)


def _generate_rating_file(all_results):
    """Generate a clean file for blind rating (no condition labels)."""
    rating_file = EVAL_DIR / "eval_blind_responses.md"

    lines = [
        "# Eval: Blind Responses for Rating",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Model: {EVAL_MODEL}",
        "",
        "Rate each response on the 6 dimensions (1-5 scale).",
        "See EVAL_FRAMEWORK.md for rating scale calibration and dimension guidance.",
        "",
        "---",
        "",
    ]

    for pid in sorted(all_results.keys(), key=int):
        result = all_results[pid]
        lines.append(f"# Prompt {pid}: {result['category']}")
        lines.append(f"")
        lines.append(f"> {result['prompt_text']}")
        lines.append(f"")

        # Show responses in label order (X, Y, Z)
        by_label = {c["label"]: c for c in result["conditions"]}
        for label in ["X", "Y", "Z"]:
            cond = by_label[label]
            lines.append(f"## Response {label}")
            lines.append(f"")
            lines.append(cond["response"])
            lines.append(f"")
            lines.append(f"---")
            lines.append(f"")

    with open(rating_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Blind rating file: {rating_file}")


# ---------------------------------------------------------------------------
# Rating Mode
# ---------------------------------------------------------------------------

def run_rate():
    """Interactive CLI for blind rating of eval responses."""
    results_file = EVAL_DIR / "eval_results.json"
    ratings_file = EVAL_DIR / "eval_ratings.json"

    if not results_file.exists():
        print("ERROR: No results file. Run --generate first.")
        return

    with open(results_file, "r", encoding="utf-8") as f:
        all_results = json.load(f)

    # Load existing ratings
    if ratings_file.exists():
        with open(ratings_file, "r", encoding="utf-8") as f:
            all_ratings = json.load(f)
    else:
        all_ratings = {}

    print("=" * 60)
    print("Eval Runner — Blind Rating")
    print("=" * 60)
    print()
    print("Rate each response on a 1-5 scale per dimension.")
    print("Rating scale: 1=stranger, 2=LinkedIn, 3=met once, 4=worked together, 5=gets me")
    print("Type 'skip' to skip a prompt, 'quit' to save and exit.")
    print()

    # Rate one dimension at a time across all responses (per framework guidance)
    for dim in DIMENSIONS:
        dim_label = DIMENSION_LABELS[dim]
        print(f"\n{'=' * 60}")
        print(f"  DIMENSION: {dim_label}")
        print(f"{'=' * 60}")

        for pid in sorted(all_results.keys(), key=int):
            result = all_results[pid]

            # Initialize ratings structure
            if pid not in all_ratings:
                all_ratings[pid] = {"ratings": {}, "notes": {}, "wrong_facts": {}}
            if dim not in all_ratings[pid]["ratings"]:
                all_ratings[pid]["ratings"][dim] = {}

            # Skip if already rated for this dimension
            existing = all_ratings[pid]["ratings"].get(dim, {})
            if len(existing) == 3:
                print(f"\n  Prompt #{pid} [{dim_label}]: already rated, skipping")
                continue

            print(f"\n  --- Prompt #{pid}: {result['category']} ---")
            print(f"  > {result['prompt_text']}")

            by_label = {c["label"]: c for c in result["conditions"]}
            for label in ["X", "Y", "Z"]:
                if label in existing:
                    continue

                cond = by_label[label]
                print(f"\n  Response {label}:")
                # Wrap long responses
                response_text = cond["response"]
                for line in response_text.split("\n"):
                    print(f"    {line}")

                while True:
                    try:
                        score_input = input(f"\n  {dim_label} for {label} (1-5, skip, quit): ").strip()
                    except (EOFError, KeyboardInterrupt):
                        score_input = "quit"

                    if score_input.lower() == "quit":
                        _save_ratings(ratings_file, all_ratings)
                        print(f"\nRatings saved. Resume with: python run_eval.py --rate")
                        return
                    if score_input.lower() == "skip":
                        break
                    try:
                        score = int(score_input)
                        if 1 <= score <= 5:
                            all_ratings[pid]["ratings"][dim][label] = score

                            # Ask for optional note on any score
                            note = input(f"  Note for {label} (enter to skip): ").strip()
                            if note:
                                if "justifications" not in all_ratings[pid]:
                                    all_ratings[pid]["justifications"] = {}
                                all_ratings[pid]["justifications"][f"{dim}_{label}"] = note

                            break
                        else:
                            print("  Please enter 1-5.")
                    except ValueError:
                        print("  Please enter 1-5, 'skip', or 'quit'.")

            # Save after each prompt
            _save_ratings(ratings_file, all_ratings)

    # After all dimensions, ask for wrong facts per prompt
    print(f"\n{'=' * 60}")
    print("  WRONG FACTS: Flag any incorrect statements")
    print(f"{'=' * 60}")
    print()
    print("For each prompt, note any factually wrong statements in any response.")
    print("Format: 'X: said I live in Dallas' or just press enter to skip.")
    print()

    for pid in sorted(all_results.keys(), key=int):
        result = all_results[pid]
        try:
            wrong = input(f"  Prompt #{pid} wrong facts (enter to skip): ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if wrong:
            all_ratings[pid]["wrong_facts"] = wrong

    _save_ratings(ratings_file, all_ratings)

    # After all dimensions, ask for condition-C detection
    print(f"\n{'=' * 60}")
    print("  PRE-REVEAL: Condition Detection")
    print(f"{'=' * 60}")
    print()
    print("Before unblinding, guess which response (X/Y/Z) is condition C (the brief)")
    print("for each prompt. This measures blinding quality.")
    print()

    detection = {}
    for pid in sorted(all_results.keys(), key=int):
        result = all_results[pid]
        try:
            guess = input(f"  Prompt #{pid} — which is C? (X/Y/Z/unsure): ").strip().upper()
        except (EOFError, KeyboardInterrupt):
            break
        if guess in ("X", "Y", "Z", "UNSURE"):
            confidence = input(f"  Confidence (low/medium/high): ").strip().lower()
            detection[pid] = {"guess": guess, "confidence": confidence}

    all_ratings["_detection"] = detection
    _save_ratings(ratings_file, all_ratings)

    print(f"\nAll ratings complete! Run: python run_eval.py --reveal")


def _save_ratings(filepath, ratings):
    """Save ratings to JSON."""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(ratings, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Reveal Mode
# ---------------------------------------------------------------------------

def run_reveal():
    """Unblind conditions and show results."""
    results_file = EVAL_DIR / "eval_results.json"
    ratings_file = EVAL_DIR / "eval_ratings.json"

    if not results_file.exists() or not ratings_file.exists():
        print("ERROR: Need both results and ratings. Run --generate and --rate first.")
        return

    with open(results_file, "r", encoding="utf-8") as f:
        all_results = json.load(f)
    with open(ratings_file, "r", encoding="utf-8") as f:
        all_ratings = json.load(f)

    print("=" * 60)
    print("Eval Runner — Reveal & Analysis")
    print("=" * 60)

    # Map labels back to conditions
    condition_scores = {"A": {d: [] for d in DIMENSIONS},
                        "B": {d: [] for d in DIMENSIONS},
                        "C": {d: [] for d in DIMENSIONS}}

    for pid in sorted(all_results.keys(), key=int):
        result = all_results[pid]
        rating = all_ratings.get(pid, {})
        label_map = result["label_map"]
        reverse_map = {v: k for k, v in label_map.items()}  # condition -> label

        print(f"\n  Prompt #{pid}: {result['prompt_text'][:60]}...")
        print(f"    Mapping: X={label_map.get('X','?')}, Y={label_map.get('Y','?')}, Z={label_map.get('Z','?')}")

        for dim in DIMENSIONS:
            dim_ratings = rating.get("ratings", {}).get(dim, {})
            for label, score in dim_ratings.items():
                condition = label_map.get(label)
                if condition:
                    condition_scores[condition][dim].append(score)

            # Show per-prompt scores by condition
            scores_by_cond = {}
            for label, score in dim_ratings.items():
                cond = label_map.get(label, "?")
                scores_by_cond[cond] = score

            if scores_by_cond:
                parts = [f"{c}={s}" for c, s in sorted(scores_by_cond.items())]
                dim_label = DIMENSION_LABELS[dim]
                print(f"    {dim_label:<28s} {', '.join(parts)}")

    # Summary table
    print(f"\n{'=' * 60}")
    print("  SUMMARY: Average Scores by Condition")
    print(f"{'=' * 60}")
    print(f"\n  {'Dimension':<28s} {'A (Base)':>10s} {'B (Raw)':>10s} {'C (Brief)':>10s} {'C-B':>8s}")
    print(f"  {'-' * 64}")

    seen_scores = {"A": [], "B": [], "C": []}

    for dim in DIMENSIONS:
        dim_label = DIMENSION_LABELS[dim]
        avgs = {}
        for cond in ["A", "B", "C"]:
            scores = condition_scores[cond][dim]
            avgs[cond] = sum(scores) / len(scores) if scores else 0

        diff = avgs["C"] - avgs["B"]
        diff_str = f"+{diff:.2f}" if diff >= 0 else f"{diff:.2f}"

        print(f"  {dim_label:<28s} {avgs['A']:>10.2f} {avgs['B']:>10.2f} {avgs['C']:>10.2f} {diff_str:>8s}")

        if dim == "seen_factor":
            for cond in ["A", "B", "C"]:
                seen_scores[cond] = condition_scores[cond][dim]

    # Overall averages
    print(f"  {'-' * 64}")
    overall = {}
    for cond in ["A", "B", "C"]:
        all_scores = []
        for dim in DIMENSIONS:
            all_scores.extend(condition_scores[cond][dim])
        overall[cond] = sum(all_scores) / len(all_scores) if all_scores else 0

    diff = overall["C"] - overall["B"]
    diff_str = f"+{diff:.2f}" if diff >= 0 else f"{diff:.2f}"
    print(f"  {'OVERALL':<28s} {overall['A']:>10.2f} {overall['B']:>10.2f} {overall['C']:>10.2f} {diff_str:>8s}")

    # Success criteria check
    print(f"\n{'=' * 60}")
    print("  SUCCESS CRITERIA")
    print(f"{'=' * 60}")

    seen_avg_b = sum(seen_scores["B"]) / len(seen_scores["B"]) if seen_scores["B"] else 0
    seen_avg_c = sum(seen_scores["C"]) / len(seen_scores["C"]) if seen_scores["C"] else 0
    seen_diff = seen_avg_c - seen_avg_b

    c_gt_a = sum(1 for dim in DIMENSIONS
                 if (sum(condition_scores["C"][dim]) / max(len(condition_scores["C"][dim]), 1)) >
                    (sum(condition_scores["A"][dim]) / max(len(condition_scores["A"][dim]), 1)))

    b_gt_a_pers = False
    if condition_scores["B"]["personalization_accuracy"] and condition_scores["A"]["personalization_accuracy"]:
        b_avg = sum(condition_scores["B"]["personalization_accuracy"]) / len(condition_scores["B"]["personalization_accuracy"])
        a_avg = sum(condition_scores["A"]["personalization_accuracy"]) / len(condition_scores["A"]["personalization_accuracy"])
        b_gt_a_pers = b_avg > a_avg

    novel_c = sum(condition_scores["C"]["novel_composition"]) / max(len(condition_scores["C"]["novel_composition"]), 1)
    novel_b = sum(condition_scores["B"]["novel_composition"]) / max(len(condition_scores["B"]["novel_composition"]), 1)

    checks = [
        (f"C > B on Seen factor by >= 1.0 (actual: {seen_diff:+.2f})", seen_diff >= 1.0),
        (f"C > A on all 6 dimensions ({c_gt_a}/6)", c_gt_a == 6),
        (f"B > A on personalization", b_gt_a_pers),
        (f"Novel composition: C > B ({novel_c:.2f} vs {novel_b:.2f})", novel_c > novel_b),
    ]

    for desc, passed in checks:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {desc}")

    # Detection analysis
    detection = all_ratings.get("_detection", {})
    if detection:
        print(f"\n{'=' * 60}")
        print("  BLINDING QUALITY")
        print(f"{'=' * 60}")

        correct = 0
        total = 0
        for pid, det in detection.items():
            if pid.startswith("_"):
                continue
            guess = det.get("guess", "")
            result = all_results.get(pid, {})
            label_map = result.get("label_map", {})
            actual_c_label = None
            for label, cond in label_map.items():
                if cond == "C":
                    actual_c_label = label
                    break

            if guess == actual_c_label:
                correct += 1
                status = "CORRECT"
            elif guess == "UNSURE":
                status = "UNSURE"
            else:
                status = "WRONG"
            total += 1
            print(f"  Prompt #{pid}: guessed {guess}, actual C={actual_c_label} — {status} ({det.get('confidence', '?')})")

        detection_rate = correct / total if total > 0 else 0
        blinding_ok = correct < 7
        print(f"\n  Detection rate: {correct}/{total} ({detection_rate:.0%})")
        print(f"  [{'PASS' if blinding_ok else 'FAIL'}] C identified on fewer than 7/10 prompts")

    # Save full analysis
    analysis_file = EVAL_DIR / "eval_analysis.json"
    analysis = {
        "condition_averages": {
            cond: {dim: (sum(scores) / len(scores) if scores else 0)
                   for dim, scores in dim_scores.items()}
            for cond, dim_scores in condition_scores.items()
        },
        "overall_averages": overall,
        "seen_factor_diff": seen_diff,
        "success_criteria": {desc: passed for desc, passed in checks},
        "analyzed_at": datetime.now().isoformat(),
    }
    with open(analysis_file, "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)
    print(f"\nAnalysis saved to: {analysis_file}")


# ---------------------------------------------------------------------------
# Summary Mode (quick view without full reveal)
# ---------------------------------------------------------------------------

def run_summary():
    """Show quick summary of ratings without full reveal."""
    ratings_file = EVAL_DIR / "eval_ratings.json"

    if not ratings_file.exists():
        print("ERROR: No ratings file. Run --rate first.")
        return

    with open(ratings_file, "r", encoding="utf-8") as f:
        all_ratings = json.load(f)

    rated_prompts = [k for k in all_ratings.keys() if not k.startswith("_")]
    total_ratings = 0
    for pid in rated_prompts:
        for dim in DIMENSIONS:
            total_ratings += len(all_ratings[pid].get("ratings", {}).get(dim, {}))

    expected = len(rated_prompts) * len(DIMENSIONS) * 3  # 3 conditions per prompt
    print(f"Rating progress: {total_ratings}/{expected} scores across {len(rated_prompts)} prompts")
    print(f"Dimensions completed: ", end="")

    for dim in DIMENSIONS:
        count = sum(len(all_ratings[pid].get("ratings", {}).get(dim, {}))
                    for pid in rated_prompts)
        expected_dim = len(rated_prompts) * 3
        print(f"{DIMENSION_LABELS[dim]}: {count}/{expected_dim}  ", end="")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="A/B/C Blind Evaluation Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_eval.py --generate              # Generate all A/B/C responses
  python run_eval.py --generate --prompt 3   # Regenerate prompt #3 only
  python run_eval.py --rate                   # Interactive blind rating
  python run_eval.py --reveal                 # Unblind and show results
  python run_eval.py --summary                # Quick rating progress check
""",
    )
    parser.add_argument("--generate", action="store_true",
                        help="Generate A/B/C responses for all prompts")
    parser.add_argument("--prompt", type=int, metavar="N",
                        help="Generate for a specific prompt ID only")
    parser.add_argument("--rate", action="store_true",
                        help="Interactive blind rating mode")
    parser.add_argument("--reveal", action="store_true",
                        help="Unblind conditions and show analysis")
    parser.add_argument("--summary", action="store_true",
                        help="Quick rating progress check")

    args = parser.parse_args()

    if args.generate:
        run_generate(prompt_id=args.prompt)
    elif args.rate:
        run_rate()
    elif args.reveal:
        run_reveal()
    elif args.summary:
        run_summary()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
