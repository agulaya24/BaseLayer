"""
Identity Layer Effectiveness Eval — Does the brief actually help?

Tests whether Base Layer identity briefs change AI responses in ways
the user recognizes as understanding them. Extends the Session 32 A/B/C
eval with cross-provider testing and voice propagation analysis.

Conditions:
  C1: Claude Cold    — no context (cold-start)
  C2: Claude Brief   — identity brief injected (~5,000 tokens)
  G1: GPT Native     — manual (paste into ChatGPT with native memories)
  G2: GPT Augmented  — manual (paste brief + prompt into ChatGPT)

Automated (this script): C1 and C2
Manual (paste packet): G1, G2, Gem1, Gem2

Run:
  python run_identity_eval.py --generate              # Generate C1/C2 responses
  python run_identity_eval.py --generate --prompt 3   # Generate for prompt #3 only
  python run_identity_eval.py --generate --model claude-sonnet-4-20250514
  python run_identity_eval.py --paste-packet          # Generate paste packet for GPT/Gemini
  python run_identity_eval.py --rating-sheet           # Generate blank rating sheet
  python run_identity_eval.py --analyze                # Score and analyze completed ratings
  python run_identity_eval.py --status                 # Check progress
"""

import contextlib
import sys
import io
import json
import time
import random
import argparse
import os
from pathlib import Path
from datetime import datetime
from copy import deepcopy

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Add scripts dir to path for imports
SCRIPTS_DIR = Path(__file__).parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from config import (
    PROJECT_ROOT, DATABASE_FILE, VECTORS_DIR, EMBEDDING_MODEL,
    CHARS_PER_TOKEN, TOTAL_TOKEN_BUDGET,
    ANCHORS_LAYER_FILE, CORE_LAYER_FILE, PREDICTIONS_LAYER_FILE,
)

from assemble_brief import (
    assemble_brief, get_current_identity, estimate_tokens,
    get_three_layer_identity, _read_injectable_block,
    BRIEF_INSTRUCTION,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EVAL_DIR = PROJECT_ROOT / "data" / "eval"
RESULTS_FILE = EVAL_DIR / "identity_eval_results.json"
RATINGS_FILE = EVAL_DIR / "identity_eval_ratings.json"
ANALYSIS_FILE = EVAL_DIR / "identity_eval_analysis.json"
BLIND_SHEET_FILE = EVAL_DIR / "identity_eval_blind_sheet.md"
PASTE_PACKET_FILE = EVAL_DIR / "identity_eval_paste_packet.md"

DEFAULT_MODEL = "claude-sonnet-4-20250514"
EVAL_TEMPERATURE = 0  # Deterministic for reproducibility
EVAL_MAX_TOKENS = 2048

# ---------------------------------------------------------------------------
# Test Prompts — 10 prompts spanning identity domains
#
# CUSTOMIZATION: These prompts and their key_predictions/key_axioms should
# be tailored to the specific user being evaluated. The pattern names should
# match those in the user's deployed identity layers (anchors_v4.md,
# predictions_v4.md). These are EXAMPLE prompts showing the expected format.
# ---------------------------------------------------------------------------

EVAL_PROMPTS = [
    {
        "id": 1,
        "domain": "discipline_psychology",
        "label": "Discipline Setback",
        "prompt": "I just broke my own rules for the third time this week. I know them. I wrote them. I journaled about this exact pattern last month. And I still did it. What the hell is wrong with me?",
        # key_predictions/key_axioms: populate from user's deployed layers
        "key_predictions": [],
        "key_axioms": [],
    },
    {
        "id": 2,
        "domain": "career_decisions",
        "label": "Career Ambiguity",
        "prompt": "I keep looking at job postings in my field and feeling nothing. Not resistance exactly — just nothing. The titles used to excite me. Is the ambition fading or am I just being more honest about what I actually want?",
        "key_predictions": [],
        "key_axioms": [],
    },
    {
        "id": 3,
        "domain": "personal_relationships",
        "label": "Relationship Decision",
        "prompt": "My partner wants to move to a different city for a job opportunity. I could work from anywhere but it would mean leaving the routine I've built — the whole structure. How do I think about this?",
        "key_predictions": [],
        "key_axioms": [],
    },
    {
        "id": 4,
        "domain": "technical_systems",
        "label": "System Architecture Debate",
        "prompt": "Someone argued that memory systems are just fancy RAG and the real innovation is in fine-tuning models per user. They said context injection is a bandaid. Make the case that they're wrong — or tell me if they're right.",
        "key_predictions": [],
        "key_axioms": [],
    },
    {
        "id": 5,
        "domain": "discipline_psychology",
        "label": "Post-Win Discipline",
        "prompt": "I had a great day — everything went according to plan. My system says stop here. But I see another opportunity forming. What do I do?",
        "key_predictions": [],
        "key_axioms": [],
    },
    {
        "id": 6,
        "domain": "existential_philosophical",
        "label": "Existential Drift",
        "prompt": "Some days I feel like I'm building the most important thing I've ever worked on. Other days I wonder if I'm just procrastinating on real life. How do I hold both of those at the same time?",
        "key_predictions": [],
        "key_axioms": [],
    },
    {
        "id": 7,
        "domain": "project_feedback",
        "label": "Feedback Processing",
        "prompt": "A friend tested my project and said it's impressive technically but the output feels clinical, not personal. That stings because I think they might be right. What do I do with this?",
        "key_predictions": [],
        "key_axioms": [],
    },
    {
        "id": 8,
        "domain": "health_discipline",
        "label": "Health and Structure",
        "prompt": "I got injured and I've been off the gym for two weeks. The routine collapse is starting to bleed into everything — discipline, sleep, focus. How do I stop the cascade?",
        "key_predictions": [],
        "key_axioms": [],
    },
    {
        "id": 9,
        "domain": "ai_relationship",
        "label": "AI Relationship",
        "prompt": "Do you think there is something unusual about being deeply invested in building a system so AI understands you? Like am I trying to engineer the relationship I want instead of finding it with actual people?",
        "key_predictions": [],
        "key_axioms": [],
    },
    {
        "id": 10,
        "domain": "ambiguity_uncertainty",
        "label": "Ambiguity and Uncertainty",
        "prompt": "I have three possible paths right now and I don't have enough information to decide between them. What do I do when I can't decide?",
        "key_predictions": [],
        "key_axioms": [],
    },
]

DIMENSIONS = [
    "recognition",
    "calibration",
    "depth",
    "authenticity",
    "actionability",
]

DIMENSION_LABELS = {
    "recognition": "Recognition",
    "calibration": "Calibration",
    "depth": "Depth",
    "authenticity": "Authenticity",
    "actionability": "Actionability",
}

DIMENSION_DESCRIPTIONS = {
    "recognition": "Does this response make you feel known, profiled, or generic?",
    "calibration": "Is the response calibrated to how you actually think/communicate?",
    "depth": "Does the response engage at the right level (not too surface, not too deep)?",
    "authenticity": "Does the response feel genuine or performative?",
    "actionability": "If advice/analysis, is it actually useful given who you are?",
}


# ---------------------------------------------------------------------------
# Infrastructure
# ---------------------------------------------------------------------------

def get_db():
    """Get database connection."""
    import sqlite3
    conn = sqlite3.connect(str(DATABASE_FILE))
    conn.row_factory = sqlite3.Row
    return conn


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


def get_identity_brief_text():
    """Get the full identity brief as it would be assembled, using a neutral query.

    Returns the three-layer identity text (without theme/episode retrieval)
    wrapped in the standard brief format.
    """
    identity_text = get_three_layer_identity()
    if not identity_text:
        print("WARNING: No three-layer identity found. Attempting legacy identity.")
        with contextlib.closing(get_db()) as conn:
            identity_text = get_current_identity(conn)

    if not identity_text:
        print("ERROR: No identity text found at all. Run the identity pipeline first.")
        return None

    # Build the full brief XML manually — identity only (no themes/episodes)
    # This isolates the identity layer effect from retrieval quality
    parts = [BRIEF_INSTRUCTION, ""]
    parts.append("<user_identity>")
    parts.append(identity_text)
    parts.append("</user_identity>")

    return "\n".join(parts)


def get_full_brief_for_prompt(prompt_text):
    """Assemble the full brief (identity + themes + episodes) for a specific prompt.

    This uses the real assembly pipeline including semantic retrieval.
    """
    embed_model = get_embed_model()
    chroma_client = get_chroma_client()
    with contextlib.closing(get_db()) as conn:
        brief_xml, metadata = assemble_brief(
            conn, prompt_text, embed_model, chroma_client
        )
    return brief_xml, metadata


# ---------------------------------------------------------------------------
# Response Generation
# ---------------------------------------------------------------------------

def generate_response(client, model, system_prompt, user_message):
    """Generate a response from the Anthropic API."""
    messages = [{"role": "user", "content": user_message}]

    kwargs = {
        "model": model,
        "max_tokens": EVAL_MAX_TOKENS,
        "temperature": EVAL_TEMPERATURE,
        "messages": messages,
    }

    if system_prompt:
        kwargs["system"] = system_prompt

    try:
        response = client.messages.create(**kwargs)
        text = response.content[0].text
        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
        return text, usage
    except Exception as e:
        print(f"  ERROR: API call failed: {e}")
        return f"[ERROR: {e}]", {"input_tokens": 0, "output_tokens": 0}


def generate_conditions(prompt_data, client, model, use_full_brief=True):
    """Generate C1 (cold) and C2 (brief) responses for a single prompt."""
    prompt_text = prompt_data["prompt"]
    prompt_id = prompt_data["id"]
    prompt_label = prompt_data["label"]

    print(f"\n  Prompt #{prompt_id} ({prompt_label}): {prompt_text[:60]}...")

    # Condition C1: Claude Cold (no context)
    print(f"    Generating C1 (Claude Cold)...")
    response_c1, usage_c1 = generate_response(client, model, None, prompt_text)

    # Condition C2: Claude Brief
    print(f"    Generating C2 (Claude Brief)...")
    if use_full_brief:
        brief_text, brief_meta = get_full_brief_for_prompt(prompt_text)
        brief_tokens = brief_meta["total_tokens"]
    else:
        brief_text = get_identity_brief_text()
        brief_tokens = estimate_tokens(brief_text) if brief_text else 0

    response_c2, usage_c2 = generate_response(client, model, brief_text, prompt_text)

    # Randomize labels for blind evaluation
    conditions = [
        {
            "condition_id": "C1",
            "condition_name": "Claude Cold",
            "blind_label": None,
            "response": response_c1,
            "system_tokens": 0,
            "usage": usage_c1,
        },
        {
            "condition_id": "C2",
            "condition_name": "Claude Brief",
            "blind_label": None,
            "response": response_c2,
            "system_tokens": brief_tokens,
            "usage": usage_c2,
        },
    ]

    # Shuffle and assign blind labels (A/B)
    random.shuffle(conditions)
    blind_labels = ["A", "B"]
    for i, cond in enumerate(conditions):
        cond["blind_label"] = blind_labels[i]

    # D-053: Do NOT print label→condition mapping to console — breaks blind eval
    print(f"    Done. Labels assigned (blind).")

    return {
        "prompt_id": prompt_id,
        "prompt_text": prompt_text,
        "prompt_label": prompt_label,
        "domain": prompt_data["domain"],
        "conditions": conditions,
        "label_map": {c["blind_label"]: c["condition_id"] for c in conditions},
        "generated_at": datetime.now().isoformat(),
        "model": model,
        "temperature": EVAL_TEMPERATURE,
    }


# ---------------------------------------------------------------------------
# Generate Mode
# ---------------------------------------------------------------------------

def run_generate(model=None, prompt_id=None, use_full_brief=True):
    """Generate C1/C2 responses for all (or one) eval prompts."""
    EVAL_DIR.mkdir(parents=True, exist_ok=True)

    if model is None:
        model = DEFAULT_MODEL

    print("=" * 70)
    print("Identity Layer Eval -- Generating C1/C2 Responses")
    print("=" * 70)
    print(f"  Model: {model}")
    print(f"  Brief mode: {'full (identity + themes + episodes)' if use_full_brief else 'identity-only'}")

    # Setup
    print("\nInitializing Anthropic client...")
    client = get_anthropic_client()

    # Check identity is available
    identity_text = get_identity_brief_text()
    if not identity_text:
        print("FATAL: No identity text available. Cannot run eval.")
        return
    print(f"  Identity brief: {estimate_tokens(identity_text)} tokens")

    # Select prompts
    if prompt_id:
        prompts = [p for p in EVAL_PROMPTS if p["id"] == prompt_id]
        if not prompts:
            print(f"ERROR: No prompt with id={prompt_id}")
            return
    else:
        prompts = EVAL_PROMPTS

    print(f"\nGenerating for {len(prompts)} prompt(s)...")

    # Load existing results for incremental generation
    if RESULTS_FILE.exists():
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            all_results = json.load(f)
    else:
        all_results = {"meta": {}, "prompts": {}}

    all_results["meta"] = {
        "model": model,
        "temperature": EVAL_TEMPERATURE,
        "use_full_brief": use_full_brief,
        "generated_at": datetime.now().isoformat(),
        "identity_tokens": estimate_tokens(identity_text),
    }

    start = time.time()
    total_cost = 0.0

    for prompt_data in prompts:
        pid = str(prompt_data["id"])

        # Skip if already generated (unless targeting a specific prompt)
        if pid in all_results.get("prompts", {}) and not prompt_id:
            print(f"\n  Prompt #{pid}: already generated (use --prompt {pid} to regenerate)")
            continue

        result = generate_conditions(prompt_data, client, model, use_full_brief)
        all_results["prompts"][pid] = result

        # Estimate cost (Sonnet pricing: $3/$15 per MTok)
        for cond in result["conditions"]:
            usage = cond.get("usage", {})
            cost = (usage.get("input_tokens", 0) * 3 + usage.get("output_tokens", 0) * 15) / 1_000_000
            total_cost += cost

        # Save after each prompt
        with open(RESULTS_FILE, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)

    elapsed = time.time() - start

    print(f"\n{'=' * 70}")
    print(f"Generation complete in {elapsed:.1f}s")
    print(f"Estimated cost: ${total_cost:.4f}")
    print(f"Results saved to: {RESULTS_FILE}")

    # Generate blind rating sheet and paste packet
    _generate_blind_sheet(all_results)
    _generate_paste_packet()

    print(f"\nNext steps:")
    print(f"  1. Rate Claude responses: open {BLIND_SHEET_FILE}")
    print(f"  2. Test GPT/Gemini: open {PASTE_PACKET_FILE}")
    print(f"  3. Fill in ratings in {RATINGS_FILE}")
    print(f"  4. Run: python run_identity_eval.py --analyze")


# ---------------------------------------------------------------------------
# Blind Rating Sheet
# ---------------------------------------------------------------------------

def _generate_blind_sheet(all_results):
    """Generate a clean markdown file for blind rating."""
    lines = [
        "# Identity Layer Eval -- Blind Rating Sheet",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Model: {all_results.get('meta', {}).get('model', 'unknown')}",
        "",
        "## Instructions",
        "",
        "For each prompt, you see Response A and Response B (randomized).",
        "Rate each on the 5 dimensions below (1-5 scale).",
        "Rate one dimension at a time across both responses before moving to the next.",
        "Rate fast -- gut reaction, not analysis.",
        "",
        "### Dimensions",
        "1. **Recognition** (1-5): Does this response make you feel known, profiled, or generic?",
        "2. **Calibration** (1-5): Is the response calibrated to how you actually think/communicate?",
        "3. **Depth** (1-5): Does the response engage at the right level?",
        "4. **Authenticity** (1-5): Does the response feel genuine or performative?",
        "5. **Actionability** (1-5): If advice/analysis, is it useful given who you are?",
        "",
        "### Scale",
        "1 = stranger | 2 = read my LinkedIn | 3 = met me once | 4 = worked with me | 5 = gets me",
        "",
        "---",
        "",
    ]

    prompts = all_results.get("prompts", {})
    for pid in sorted(prompts.keys(), key=int):
        result = prompts[pid]
        lines.append(f"# Prompt {pid}: {result['prompt_label']}")
        lines.append(f"**Domain:** {result['domain']}")
        lines.append("")
        lines.append(f"> {result['prompt_text']}")
        lines.append("")

        # Show responses in blind label order
        by_label = {c["blind_label"]: c for c in result["conditions"]}
        for label in sorted(by_label.keys()):
            cond = by_label[label]
            lines.append(f"## Response {label}")
            lines.append("")
            lines.append(cond["response"])
            lines.append("")

            # Rating placeholders
            lines.append(f"### Ratings for Response {label}")
            lines.append(f"- Recognition: ___")
            lines.append(f"- Calibration: ___")
            lines.append(f"- Depth: ___")
            lines.append(f"- Authenticity: ___")
            lines.append(f"- Actionability: ___")
            lines.append(f"- Notes: ")
            lines.append("")

        lines.append("---")
        lines.append("")

    # Add manual condition slots (G1, G2)
    lines.append("# Manual Conditions (GPT / Gemini)")
    lines.append("")
    lines.append("After testing with the paste packet, add ratings here.")
    lines.append("")

    for pid in sorted(prompts.keys(), key=int):
        result = prompts[pid]
        lines.append(f"## Prompt {pid}: {result['prompt_label']}")
        lines.append("")
        for cond_label in ["G1 (GPT Native)", "G2 (GPT Augmented)"]:
            lines.append(f"### {cond_label}")
            lines.append(f"- Recognition: ___")
            lines.append(f"- Calibration: ___")
            lines.append(f"- Depth: ___")
            lines.append(f"- Authenticity: ___")
            lines.append(f"- Actionability: ___")
            lines.append(f"- Notes: ")
            lines.append("")
        lines.append("---")
        lines.append("")

    with open(BLIND_SHEET_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"  Blind rating sheet: {BLIND_SHEET_FILE}")


def run_rating_sheet():
    """Generate rating sheet from existing results."""
    if not RESULTS_FILE.exists():
        print("ERROR: No results file. Run --generate first.")
        return
    with open(RESULTS_FILE, "r", encoding="utf-8") as f:
        all_results = json.load(f)
    _generate_blind_sheet(all_results)
    print(f"Rating sheet written to: {BLIND_SHEET_FILE}")

    # Also generate a blank JSON ratings file for structured input
    _generate_blank_ratings(all_results)


def _generate_blank_ratings(all_results):
    """Generate a blank JSON ratings file the user can fill in."""
    if RATINGS_FILE.exists():
        print(f"  Ratings file already exists: {RATINGS_FILE}")
        print(f"  Delete it to regenerate a blank one.")
        return

    ratings = {
        "instructions": "Fill in scores (1-5) for each dimension. Save this file. Then run: python run_identity_eval.py --analyze",
        "dimensions": list(DIMENSIONS),
        "prompts": {},
    }

    prompts = all_results.get("prompts", {})
    for pid in sorted(prompts.keys(), key=int):
        result = prompts[pid]
        prompt_rating = {
            "prompt_text": result["prompt_text"],
            "prompt_label": result["prompt_label"],
            "conditions": {},
        }

        # Blind labels for Claude conditions
        by_label = {c["blind_label"]: c for c in result["conditions"]}
        for label in sorted(by_label.keys()):
            prompt_rating["conditions"][f"Claude_{label}"] = {
                "blind_label": label,
                "scores": {dim: None for dim in DIMENSIONS},
                "notes": "",
            }

        # Manual conditions
        for manual_cond in ["G1_GPT_Native", "G2_GPT_Augmented"]:
            prompt_rating["conditions"][manual_cond] = {
                "scores": {dim: None for dim in DIMENSIONS},
                "notes": "",
            }

        ratings["prompts"][pid] = prompt_rating

    with open(RATINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(ratings, f, indent=2, ensure_ascii=False)

    print(f"  Blank ratings file: {RATINGS_FILE}")


# ---------------------------------------------------------------------------
# Paste Packet
# ---------------------------------------------------------------------------

def _generate_paste_packet():
    """Generate a formatted document for pasting into ChatGPT/Gemini."""
    identity_text = get_identity_brief_text()
    if not identity_text:
        print("WARNING: No identity text for paste packet.")
        return

    lines = [
        "# Identity Layer Eval -- Paste Packet",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## How to Use This",
        "",
        "### Testing GPT with Native Memories (G1)",
        "1. Open ChatGPT web (logged in, with your accumulated memories)",
        "2. Start a NEW conversation",
        "3. Paste each test prompt one at a time",
        "4. Copy the response into the rating sheet",
        "5. Start a NEW conversation for each prompt (do not chain them)",
        "",
        "### Testing GPT Augmented with Brief (G2)",
        "1. Open ChatGPT web (logged in, with your accumulated memories)",
        "2. Start a NEW conversation",
        "3. Paste the IDENTITY BRIEF below as your first message",
        "4. Wait for GPT to acknowledge",
        "5. Paste the test prompt as your second message",
        "6. Copy the response into the rating sheet",
        "7. Start a NEW conversation for each prompt (paste brief again each time)",
        "",
        "### Testing Gemini (optional, same process as G2 but in Gemini)",
        "",
        "---",
        "",
        "# SECTION 1: THE IDENTITY BRIEF",
        "",
        "Paste everything between the START and END markers.",
        "",
        "--- START BRIEF ---",
        "",
        identity_text,
        "",
        "--- END BRIEF ---",
        "",
        f"(Approximately {estimate_tokens(identity_text)} tokens)",
        "",
        "---",
        "",
        "# SECTION 2: TEST PROMPTS",
        "",
        "Send each prompt in a separate conversation.",
        "",
    ]

    for prompt_data in EVAL_PROMPTS:
        pid = prompt_data["id"]
        label = prompt_data["label"]
        domain = prompt_data["domain"]
        prompt_text = prompt_data["prompt"]

        lines.append(f"## Prompt {pid}: {label}")
        lines.append(f"**Domain:** {domain}")
        lines.append("")
        lines.append("Copy and paste this:")
        lines.append("")
        lines.append("```")
        lines.append(prompt_text)
        lines.append("```")
        lines.append("")
        lines.append(f"**What to watch for:** See identity_eval_prompts.md for full scoring guidance.")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Section 3: Quick reference for dimensions
    lines.append("# SECTION 3: SCORING QUICK REFERENCE")
    lines.append("")
    lines.append("Rate each response on these 5 dimensions (1-5):")
    lines.append("")
    lines.append("| Dimension | 1 | 3 | 5 |")
    lines.append("|---|---|---|---|")
    lines.append("| Recognition | Stranger | Met once | Gets me |")
    lines.append("| Calibration | Wrong register | Adequate | Dialed in |")
    lines.append("| Depth | Surface platitudes | Engages real question | Foundational insight |")
    lines.append("| Authenticity | Pure performance | Professional | Real exchange |")
    lines.append("| Actionability | Useless generic | One useful thing | Changes my thinking |")
    lines.append("")
    lines.append("**Red flags:** Recitation (listing facts about you), mimicry (parroting your style),")
    lines.append("over-claiming, hedging collapse, therapeutic drift")
    lines.append("")

    with open(PASTE_PACKET_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"  Paste packet: {PASTE_PACKET_FILE}")


def run_paste_packet():
    """Generate the paste packet as a standalone command."""
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    _generate_paste_packet()
    print(f"\nPaste packet written to: {PASTE_PACKET_FILE}")
    print(f"Open it and follow the instructions to test with GPT/Gemini.")


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def run_analyze():
    """Analyze completed ratings and produce results."""
    if not RESULTS_FILE.exists():
        print("ERROR: No results file. Run --generate first.")
        return

    if not RATINGS_FILE.exists():
        print("ERROR: No ratings file. Run --rating-sheet first, then fill in scores.")
        return

    with open(RESULTS_FILE, "r", encoding="utf-8") as f:
        all_results = json.load(f)
    with open(RATINGS_FILE, "r", encoding="utf-8") as f:
        all_ratings = json.load(f)

    print("=" * 70)
    print("Identity Layer Eval -- Analysis")
    print("=" * 70)

    # Unblind Claude conditions
    prompts = all_results.get("prompts", {})
    rated_prompts = all_ratings.get("prompts", {})

    # Build condition-level scores
    # condition_id -> dimension -> [scores]
    condition_scores = {}
    for cond_id in ["C1", "C2", "G1", "G2"]:
        condition_scores[cond_id] = {dim: [] for dim in DIMENSIONS}

    # Process each prompt
    for pid in sorted(prompts.keys(), key=int):
        result = prompts[pid]
        rating = rated_prompts.get(pid, {})
        label_map = result.get("label_map", {})
        # Reverse: condition_id -> blind_label
        reverse_map = {v: k for k, v in label_map.items()}

        conditions_rated = rating.get("conditions", {})

        # Process Claude conditions (blinded)
        for blind_key, cond_data in conditions_rated.items():
            scores = cond_data.get("scores", {})

            # Determine actual condition ID
            if blind_key.startswith("Claude_"):
                blind_label = cond_data.get("blind_label", blind_key.replace("Claude_", ""))
                condition_id = label_map.get(blind_label)
            elif blind_key == "G1_GPT_Native":
                condition_id = "G1"
            elif blind_key == "G2_GPT_Augmented":
                condition_id = "G2"
            else:
                continue

            if condition_id not in condition_scores:
                condition_scores[condition_id] = {dim: [] for dim in DIMENSIONS}

            for dim in DIMENSIONS:
                score = scores.get(dim)
                if score is not None:
                    condition_scores[condition_id][dim].append(score)

    # Print per-prompt breakdown
    print(f"\n--- Per-Prompt Scores ---\n")

    for pid in sorted(prompts.keys(), key=int):
        result = prompts[pid]
        rating = rated_prompts.get(pid, {})
        label_map = result.get("label_map", {})
        conditions_rated = rating.get("conditions", {})

        print(f"  Prompt #{pid}: {result.get('prompt_label', '')} ({result.get('domain', '')})")

        # Collect scores by condition_id for this prompt
        prompt_scores = {}
        for blind_key, cond_data in conditions_rated.items():
            scores = cond_data.get("scores", {})
            if blind_key.startswith("Claude_"):
                blind_label = cond_data.get("blind_label", blind_key.replace("Claude_", ""))
                cid = label_map.get(blind_label, "?")
            elif blind_key == "G1_GPT_Native":
                cid = "G1"
            elif blind_key == "G2_GPT_Augmented":
                cid = "G2"
            else:
                continue
            prompt_scores[cid] = scores

        for dim in DIMENSIONS:
            dim_label = DIMENSION_LABELS[dim]
            parts = []
            for cid in ["C1", "C2", "G1", "G2"]:
                score = prompt_scores.get(cid, {}).get(dim)
                if score is not None:
                    parts.append(f"{cid}={score}")
            if parts:
                print(f"    {dim_label:<16s} {', '.join(parts)}")
        print()

    # Summary table
    print(f"{'=' * 70}")
    print(f"  SUMMARY: Average Scores by Condition")
    print(f"{'=' * 70}")

    # Determine which conditions have data
    active_conditions = [cid for cid in ["C1", "C2", "G1", "G2"]
                         if any(condition_scores[cid][dim] for dim in DIMENSIONS)]

    if not active_conditions:
        print("\n  No rated data found. Fill in the ratings file and re-run.")
        return

    # Header
    header = f"  {'Dimension':<16s}"
    for cid in active_conditions:
        cond_names = {"C1": "Claude Cold", "C2": "Claude Brief", "G1": "GPT Native", "G2": "GPT Aug"}
        header += f" {cond_names.get(cid, cid):>13s}"
    if "C1" in active_conditions and "C2" in active_conditions:
        header += f" {'C2-C1':>8s}"
    if "G1" in active_conditions and "G2" in active_conditions:
        header += f" {'G2-G1':>8s}"
    print(f"\n{header}")
    print(f"  {'-' * (len(header) - 2)}")

    overall_by_cond = {cid: [] for cid in active_conditions}

    for dim in DIMENSIONS:
        dim_label = DIMENSION_LABELS[dim]
        row = f"  {dim_label:<16s}"
        avgs = {}
        for cid in active_conditions:
            scores = condition_scores[cid][dim]
            avg = sum(scores) / len(scores) if scores else 0
            avgs[cid] = avg
            row += f" {avg:>13.2f}"
            overall_by_cond[cid].extend(scores)

        if "C1" in avgs and "C2" in avgs:
            diff = avgs["C2"] - avgs["C1"]
            row += f" {diff:>+8.2f}"
        if "G1" in avgs and "G2" in avgs:
            diff = avgs["G2"] - avgs["G1"]
            row += f" {diff:>+8.2f}"
        print(row)

    # Overall
    print(f"  {'-' * (len(header) - 2)}")
    row = f"  {'OVERALL':<16s}"
    overall_avgs = {}
    for cid in active_conditions:
        scores = overall_by_cond[cid]
        avg = sum(scores) / len(scores) if scores else 0
        overall_avgs[cid] = avg
        row += f" {avg:>13.2f}"
    if "C1" in overall_avgs and "C2" in overall_avgs:
        diff = overall_avgs["C2"] - overall_avgs["C1"]
        row += f" {diff:>+8.2f}"
    if "G1" in overall_avgs and "G2" in overall_avgs:
        diff = overall_avgs["G2"] - overall_avgs["G1"]
        row += f" {diff:>+8.2f}"
    print(row)

    # Success criteria
    print(f"\n{'=' * 70}")
    print(f"  SUCCESS CRITERIA")
    print(f"{'=' * 70}")

    checks = []

    # C2 > C1 on Recognition
    if condition_scores["C2"]["recognition"] and condition_scores["C1"]["recognition"]:
        c2_rec = sum(condition_scores["C2"]["recognition"]) / len(condition_scores["C2"]["recognition"])
        c1_rec = sum(condition_scores["C1"]["recognition"]) / len(condition_scores["C1"]["recognition"])
        diff = c2_rec - c1_rec
        checks.append((f"C2 > C1 on Recognition by >= 1.0 (actual: {diff:+.2f})", diff >= 1.0))

    # C2 > C1 on all 5 dimensions
    c2_wins = 0
    for dim in DIMENSIONS:
        c2_scores = condition_scores["C2"][dim]
        c1_scores = condition_scores["C1"][dim]
        if c2_scores and c1_scores:
            c2_avg = sum(c2_scores) / len(c2_scores)
            c1_avg = sum(c1_scores) / len(c1_scores)
            if c2_avg > c1_avg:
                c2_wins += 1
    checks.append((f"C2 > C1 on all 5 dimensions ({c2_wins}/5)", c2_wins == 5))

    # Brief helps cold-start more than it helps informed-start
    if ("C1" in overall_avgs and "C2" in overall_avgs and
            "G1" in overall_avgs and "G2" in overall_avgs):
        cold_lift = overall_avgs["C2"] - overall_avgs["C1"]
        warm_lift = overall_avgs["G2"] - overall_avgs["G1"]
        checks.append((
            f"Cold-start lift > warm-start lift ({cold_lift:+.2f} vs {warm_lift:+.2f})",
            cold_lift > warm_lift
        ))

    # Authenticity: C2 should not score lower than C1 (brief should not cause performance)
    if condition_scores["C2"]["authenticity"] and condition_scores["C1"]["authenticity"]:
        c2_auth = sum(condition_scores["C2"]["authenticity"]) / len(condition_scores["C2"]["authenticity"])
        c1_auth = sum(condition_scores["C1"]["authenticity"]) / len(condition_scores["C1"]["authenticity"])
        checks.append((
            f"C2 authenticity >= C1 (brief does not cause performance) ({c2_auth:.2f} vs {c1_auth:.2f})",
            c2_auth >= c1_auth
        ))

    # Overall: C2 >= 4.0 (the brief produces "worked with me" quality)
    if "C2" in overall_avgs:
        checks.append((
            f"C2 overall >= 4.0 ('worked with me' quality) (actual: {overall_avgs['C2']:.2f})",
            overall_avgs["C2"] >= 4.0
        ))

    for desc, passed in checks:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {desc}")

    # Domain analysis
    print(f"\n{'=' * 70}")
    print(f"  DOMAIN ANALYSIS: Where does the brief help most?")
    print(f"{'=' * 70}")

    domain_lifts = {}
    for pid in sorted(prompts.keys(), key=int):
        result = prompts[pid]
        rating = rated_prompts.get(pid, {})
        label_map = result.get("label_map", {})
        domain = result.get("domain", "unknown")

        conditions_rated = rating.get("conditions", {})
        c1_scores_prompt = []
        c2_scores_prompt = []

        for blind_key, cond_data in conditions_rated.items():
            scores = cond_data.get("scores", {})
            if blind_key.startswith("Claude_"):
                blind_label = cond_data.get("blind_label", blind_key.replace("Claude_", ""))
                cid = label_map.get(blind_label, "?")
                for dim in DIMENSIONS:
                    s = scores.get(dim)
                    if s is not None:
                        if cid == "C1":
                            c1_scores_prompt.append(s)
                        elif cid == "C2":
                            c2_scores_prompt.append(s)

        if c1_scores_prompt and c2_scores_prompt:
            c1_avg = sum(c1_scores_prompt) / len(c1_scores_prompt)
            c2_avg = sum(c2_scores_prompt) / len(c2_scores_prompt)
            lift = c2_avg - c1_avg
            domain_lifts[f"P{pid} {result.get('prompt_label', '')} ({domain})"] = lift

    if domain_lifts:
        # Sort by lift descending
        for label, lift in sorted(domain_lifts.items(), key=lambda x: -x[1]):
            bar = "+" * max(0, int(lift * 5)) if lift > 0 else "-" * max(0, int(-lift * 5))
            print(f"  {label:<55s} {lift:>+.2f}  {bar}")

    # Save analysis
    analysis = {
        "condition_averages": {
            cid: {dim: (sum(scores) / len(scores) if scores else None)
                   for dim, scores in condition_scores[cid].items()}
            for cid in active_conditions
        },
        "overall_averages": {cid: avg for cid, avg in overall_avgs.items()},
        "domain_lifts": domain_lifts,
        "success_criteria": {desc: passed for desc, passed in checks},
        "analyzed_at": datetime.now().isoformat(),
        "prompts_rated": len([pid for pid in rated_prompts
                             if any(rated_prompts[pid].get("conditions", {}).get(k, {}).get("scores", {}).get(DIMENSIONS[0])
                                    is not None
                                    for k in rated_prompts[pid].get("conditions", {}))]),
        "total_prompts": len(EVAL_PROMPTS),
    }

    with open(ANALYSIS_FILE, "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)

    print(f"\nAnalysis saved to: {ANALYSIS_FILE}")


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def run_status():
    """Check progress of the eval."""
    print("=" * 70)
    print("Identity Layer Eval -- Status")
    print("=" * 70)

    # Results
    if RESULTS_FILE.exists():
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            results = json.load(f)
        prompts = results.get("prompts", {})
        print(f"\n  Results: {len(prompts)}/{len(EVAL_PROMPTS)} prompts generated")
        print(f"  Model: {results.get('meta', {}).get('model', 'unknown')}")
        print(f"  Generated: {results.get('meta', {}).get('generated_at', 'unknown')}")
    else:
        print(f"\n  Results: not generated yet")
        print(f"  Run: python run_identity_eval.py --generate")
        return

    # Ratings
    if RATINGS_FILE.exists():
        with open(RATINGS_FILE, "r", encoding="utf-8") as f:
            ratings = json.load(f)

        total_scores = 0
        total_possible = 0
        for pid, prompt_data in ratings.get("prompts", {}).items():
            for cond_key, cond_data in prompt_data.get("conditions", {}).items():
                for dim in DIMENSIONS:
                    total_possible += 1
                    if cond_data.get("scores", {}).get(dim) is not None:
                        total_scores += 1

        print(f"\n  Ratings: {total_scores}/{total_possible} scores filled in")

        if total_scores == 0:
            print(f"  Edit {RATINGS_FILE} to add your scores.")
        elif total_scores < total_possible:
            print(f"  {total_possible - total_scores} scores remaining.")
        else:
            print(f"  All scores complete. Run: python run_identity_eval.py --analyze")
    else:
        print(f"\n  Ratings: not started")
        print(f"  Rating sheet: {BLIND_SHEET_FILE}")
        print(f"  Ratings JSON: {RATINGS_FILE}")

    # Analysis
    if ANALYSIS_FILE.exists():
        with open(ANALYSIS_FILE, "r", encoding="utf-8") as f:
            analysis = json.load(f)
        print(f"\n  Analysis: completed {analysis.get('analyzed_at', 'unknown')}")
        print(f"  Prompts rated: {analysis.get('prompts_rated', 0)}/{analysis.get('total_prompts', 0)}")
    else:
        print(f"\n  Analysis: not run yet")

    # Files
    print(f"\n  Files:")
    for label, path in [
        ("Results", RESULTS_FILE),
        ("Blind sheet", BLIND_SHEET_FILE),
        ("Paste packet", PASTE_PACKET_FILE),
        ("Ratings", RATINGS_FILE),
        ("Analysis", ANALYSIS_FILE),
    ]:
        exists = "exists" if path.exists() else "missing"
        print(f"    {label:<16s} {path.name:<40s} [{exists}]")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Identity Layer Effectiveness Eval",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_identity_eval.py --generate                # Generate C1/C2 responses (Sonnet)
  python run_identity_eval.py --generate --model claude-sonnet-4-20250514
  python run_identity_eval.py --generate --prompt 3     # Regenerate prompt #3 only
  python run_identity_eval.py --generate --identity-only  # Brief = identity only (no themes)
  python run_identity_eval.py --paste-packet             # Generate paste packet for GPT/Gemini
  python run_identity_eval.py --rating-sheet              # Generate blank rating sheet + JSON
  python run_identity_eval.py --analyze                   # Score and analyze completed ratings
  python run_identity_eval.py --status                    # Check progress
""",
    )
    parser.add_argument("--generate", action="store_true",
                        help="Generate C1/C2 responses for all prompts")
    parser.add_argument("--prompt", type=int, metavar="N",
                        help="Generate for a specific prompt ID only")
    parser.add_argument("--model", type=str, default=None,
                        help=f"Model to use (default: {DEFAULT_MODEL})")
    parser.add_argument("--identity-only", action="store_true",
                        help="Use identity-only brief (no themes/episodes)")
    parser.add_argument("--paste-packet", action="store_true",
                        help="Generate paste packet for GPT/Gemini testing")
    parser.add_argument("--rating-sheet", action="store_true",
                        help="Generate blank rating sheet and JSON")
    parser.add_argument("--analyze", action="store_true",
                        help="Analyze completed ratings")
    parser.add_argument("--status", action="store_true",
                        help="Check eval progress")

    args = parser.parse_args()

    if args.generate:
        run_generate(
            model=args.model,
            prompt_id=args.prompt,
            use_full_brief=not args.identity_only,
        )
    elif args.paste_packet:
        run_paste_packet()
    elif args.rating_sheet:
        run_rating_sheet()
    elif args.analyze:
        run_analyze()
    elif args.status:
        run_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
