"""
D-056 Extraction Prompt Eval Harness

A/B testing for extraction prompt variants. Runs multiple prompts against
the same conversations, auto-scores on quality dimensions, and produces
a comparison report. Includes Collective (Opus) qualitative review.

Variants:
  A: Current baseline (free-text fact field, 8-field schema)
  B: Subject-stripped + few-shot (Mem0-style)
  C: Structured predicates ({subject, predicate, object, qualifier})
  D: Hybrid best-of-all (C schema + subject stripping + temporal precision + few-shot)

Run:
  python eval_extraction.py --select-test-set       # Pick 20 conversations
  python eval_extraction.py --generate               # Run all variants on test set
  python eval_extraction.py --generate --variant B   # Run single variant
  python eval_extraction.py --score                  # Score all generated results
  python eval_extraction.py --compare                # Side-by-side comparison report
  python eval_extraction.py --examples 5             # Show N random fact comparisons
  python eval_extraction.py --collective             # Opus Collective qualitative review
"""

import argparse
import contextlib
import json
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import get_db
from llm_provider import call_llm, estimate_cost


# ==========================================================================
# Constants
# ==========================================================================

EVAL_DIR = Path(__file__).parent.parent / "data" / "eval"
TEST_SET_FILE = EVAL_DIR / "extraction_test_set.json"
VARIANTS = ["A", "B", "C", "D"]

# Stop words — matches score_facts.py get_fact_keywords() exactly
STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "has", "have", "had",
    "user", "they", "their", "them", "this", "that", "with", "from",
    "for", "and", "but", "not", "very", "also", "been", "being",
    "about", "into", "some", "than", "more", "most", "other",
    "what", "when", "where", "which", "who", "how", "all", "each",
    "does", "did", "will", "would", "could", "should", "may", "might",
    "can", "using", "used", "uses", "like", "likes", "interested",
    "in", "on", "at", "to", "of", "by", "as", "or", "if", "so",
    "just", "get", "got", "its", "one", "two", "way", "new", "own",
    "now", "still", "well", "back", "even", "much", "many", "made",
    "make", "over", "such", "take", "only", "come", "good", "give",
    "going", "want", "wants", "need", "needs", "think", "things",
    "thing", "really", "know", "said", "says", "work", "working",
    "works", "see", "time", "first", "last", "long", "great", "little",
    "right", "look", "day", "set", "try", "ask", "put", "keep",
    "let", "say", "help", "start", "started", "seems", "seem",
    "out", "off", "end", "times", "week", "weeks", "year", "years",
    "month", "months", "per", "down", "after", "before", "through",
    "around", "between", "under", "during", "away", "both", "same",
    "another", "since", "there", "here", "went", "done", "found",
    "able", "part", "feel", "feels", "tend", "tends", "often",
    "usually", "currently", "likely", "early", "late", "rather",
    "quite", "already", "enough", "taking", "having", "being",
    "doing", "coming", "getting", "making", "looking", "trying",
}

# Phrases that indicate template/boilerplate extraction
TEMPLATE_PHRASES = [
    "the user is", "the user has", "the user was", "the user does",
    "the user will", "the user would", "the user can",
    "is interested in", "has been", "seems to", "appears to",
    "is considering", "is concerned about",
]

# Constrained predicate vocabulary for Variant C/D (~30 canonical verbs)
CONSTRAINED_PREDICATES = [
    "owns", "values", "practices", "studies", "prefers", "avoids",
    "works_at", "lives_in", "married_to", "raised_in", "graduated_from",
    "manages", "builds", "trades", "believes", "fears", "enjoys",
    "dislikes", "struggles_with", "excels_at", "identifies_as",
    "maintains", "follows", "aspires_to", "lost", "founded",
    "parents", "experienced", "learned", "decided", "prioritizes",
]

# Scoring weights
SCORE_WEIGHTS = {
    "lexical_density": 0.25,
    "specificity": 0.20,
    "keyword_extractability": 0.20,
    "template_avoidance": 0.20,
    "brevity": 0.15,
}


# ==========================================================================
# JSON Schemas
# ==========================================================================

# Variant A/B: free-text fact field (matches extract_facts.py EXTRACT_SCHEMA)
BASELINE_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "fact": {"type": "string"},
                    "category": {"type": "string"},
                    "subject": {"type": "string"},
                    "intent": {"type": "string"},
                    "temporal": {"type": "string"},
                    "fact_class": {"type": "string"},
                    "knowledge_tier": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["fact", "category", "confidence"],
            },
        }
    },
    "required": ["facts"],
}

# Variant C/D: structured predicate triple
STRUCTURED_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "predicate": {"type": "string"},
                    "object": {"type": "string"},
                    "qualifier": {"type": "string"},
                    "category": {"type": "string"},
                    "temporal": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["subject", "predicate", "object", "category", "confidence"],
            },
        }
    },
    "required": ["facts"],
}


# ==========================================================================
# Test Set Selection
# ==========================================================================

def select_test_conversations():
    """Pick 20 conversations by fact-count distribution. Saves to JSON manifest.

    CONTAMINATION GUARDS:
    - Excludes Claude Code sessions (source='claude_code'): these are ~90% code/tool
      output and use a different extraction path (D-048 identity-only). Including them
      would skew results with non-personal content.
    - Existing extracted facts are used ONLY for bucketing (selecting conversations
      by difficulty). They are NOT input to extraction — extraction runs against
      raw messages only.
    - The Collective review (--collective) is a one-shot qualitative assessment.
      Its output is never fed back into extraction or scoring.
    """
    EVAL_DIR.mkdir(parents=True, exist_ok=True)

    with contextlib.closing(get_db()) as conn:
        # Get fact counts per conversation.
        # EXCLUDE claude_code sessions — they use a specialized extraction path (D-048)
        # and contain mostly project/code content, not personal conversations.
        rows = conn.execute("""
            SELECT mf.source_conversation_id, c.title, c.source,
                   COUNT(*) as fact_count,
                   SUM(CASE WHEN mf.fact_text LIKE 'The user is%' THEN 1 ELSE 0 END) as template_count
            FROM memory_facts mf
            JOIN conversations c ON c.id = mf.source_conversation_id
            WHERE mf.superseded_by IS NULL
              AND mf.source_conversation_id IS NOT NULL
              AND c.source != 'claude_code'
            GROUP BY mf.source_conversation_id
            HAVING fact_count >= 1
            ORDER BY fact_count DESC
        """).fetchall()

        if not rows:
            print("ERROR: No conversations with extracted facts found.")
            return

        # Bucket conversations
        high = [r for r in rows if r["fact_count"] > 15]
        medium = [r for r in rows if 5 <= r["fact_count"] <= 15]
        low = [r for r in rows if 1 <= r["fact_count"] < 5]
        template_heavy = [r for r in rows
                          if r["fact_count"] >= 3
                          and r["template_count"] / r["fact_count"] > 0.6]

        print(f"Available: {len(high)} high, {len(medium)} medium, "
              f"{len(low)} low, {len(template_heavy)} template-heavy")

        # Sample from each bucket
        selected = []

        for bucket, label, count in [
            (high, "high", 5),
            (medium, "medium", 5),
            (low, "low", 5),
            (template_heavy, "template_heavy", 5),
        ]:
            # Avoid duplicates across buckets
            available = [r for r in bucket
                         if r["source_conversation_id"] not in
                         {s["conversation_id"] for s in selected}]
            sample = random.sample(available, min(count, len(available)))
            for r in sample:
                selected.append({
                    "conversation_id": r["source_conversation_id"],
                    "title": r["title"],
                    "source": r["source"],
                    "fact_count": r["fact_count"],
                    "template_count": r["template_count"],
                    "bucket": label,
                })

        # Get message counts
        for entry in selected:
            msg_count = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
                (entry["conversation_id"],)
            ).fetchone()[0]
            entry["message_count"] = msg_count

    manifest = {
        "selected_at": time.strftime("%Y-%m-%d %H:%M"),
        "total_conversations": len(selected),
        "conversations": selected,
    }

    with open(TEST_SET_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"\nSelected {len(selected)} conversations:")
    for entry in selected:
        print(f"  [{entry['bucket']:<15}] {entry['fact_count']:>3} facts | "
              f"{entry['message_count']:>3} msgs | {entry['title'][:50]}")
    print(f"\nSaved to: {TEST_SET_FILE}")


# ==========================================================================
# Conversation Loading
# ==========================================================================

def load_conversation_text(conn, conv_id):
    """Load and format conversation messages (same logic as extract_facts.py)."""
    messages = conn.execute("""
        SELECT role, content_text FROM messages
        WHERE conversation_id = ?
        ORDER BY created_at
    """, (conv_id,)).fetchall()

    conv_text = ""
    for msg in messages:
        role = msg["role"].capitalize()
        text = (msg["content_text"] or "")[:1500]
        conv_text += f"{role}: {text}\n"
        if len(conv_text) > 12000:
            conv_text += "\n[conversation continues...]\n"
            break

    return conv_text


# ==========================================================================
# Prompt Building
# ==========================================================================

def build_variant_prompt(variant, conv_title, conv_text):
    """Build extraction prompt for the given variant."""

    if variant == "A":
        # Exact baseline from extract_facts.py lines 666-687
        return f"""You are extracting personal facts about a user from their conversation with an AI assistant.

Conversation title: "{conv_title}"

{conv_text}

Extract facts about the USER. For each fact, identify:
- WHO the fact is about (the user, or someone else like their wife, friend, colleague)
- WHAT the user's relationship is to this fact (does this, is learning about, asked about, used to do)
- Whether this is CURRENT or PAST
- Whether this is an EVENT or STATE:
  - EVENT: Something that happened. A one-time occurrence, milestone, or biographical anchor. Events are immutable — they happened and cannot be "un-happened." Examples: graduated, got married, founded a company, lost a parent, shipped a product.
  - STATE: Something currently true about the person. A mutable condition that could change over time. Examples: current job, wake-up time, active project, living situation, trading strategy, current habits.
- Knowledge tier (D-039):
  - IDENTITY: Who this person IS. Biographical anchors, values, behavioral patterns, durable preferences, proven skills. Would appear in a biography. Stable over months/years.
  - SITUATIONAL: Current mutable conditions true NOW, persisting weeks/months. Active projects, employment, living situation, ongoing opinions.
  - CONTEXT: One-off conversation artifacts. Product lookups, specific task details, debugging sessions, specific trade setups. Only relevant within this conversation.

Focus on: Biography, Preferences, Projects, Relationships, Interests, Skills, Values, Habits, Opinions, Goals, Negative traits, Reasoning patterns, Emotional triggers, Interaction preferences, Foundational beliefs
Do NOT extract trivial conversation artifacts (specific product searches, debugging steps, one-off lookups) unless they reveal something durable about the person.

Return a JSON object with a "facts" array."""

    elif variant == "B":
        # Subject-stripped + few-shot (Mem0-style)
        return f"""You are extracting personal facts about a user from their conversation with an AI assistant.

Conversation title: "{conv_title}"

{conv_text}

Extract facts about the USER. Write each fact in third person WITHOUT "The user" prefix. Start with the action, attribute, or relationship directly.

Examples of the format we want:
  BAD:  "The user is interested in Formula 1 racing"
  GOOD: "Follows Formula 1 racing actively"

  BAD:  "The user has been considering buying a new car"
  GOOD: "Considering purchasing a new vehicle"

  BAD:  "The user seems to value privacy in their projects"
  GOOD: "Values privacy as a core project principle"

  BAD:  "The user is a software architect who works remotely"
  GOOD: "Software architect, works remotely"

  BAD:  "The user has a spouse named Jordan"
  GOOD: "Married to Jordan"

For each fact, also identify:
- WHO the fact is about (the user, or someone in their life)
- WHAT the user's relationship is to this fact (does, learning, asked about, used to do)
- Whether this is CURRENT or PAST
- Whether this is an EVENT (one-time occurrence) or STATE (mutable condition)
- Knowledge tier: IDENTITY (durable, biographical) / SITUATIONAL (current, weeks-months) / CONTEXT (one-off artifact)

Focus on durable identity facts. Skip trivial conversation artifacts.

Return a JSON object with a "facts" array."""

    elif variant == "C":
        # Structured predicates with constrained vocabulary
        predicates_str = ", ".join(CONSTRAINED_PREDICATES)
        return f"""You are extracting personal facts about a user from their conversation with an AI assistant.

Conversation title: "{conv_title}"

{conv_text}

Extract facts about the USER as structured triples.

For each fact, provide:
- subject: Who the fact is about. Use the person's name if known, otherwise "user".
- predicate: The relationship or attribute. MUST be one of: {predicates_str}
- object: The specific value, entity, or description. Be precise and concrete.
- qualifier: Temporal or conditional context (e.g., "since 2020", "when stressed", "as of 2024"). If temporal scope is unclear, use "unknown" rather than guessing.
- category: One of: preference, biography, project, relationship, interest, skill, value, habit, opinion, goal, negative_trait
- temporal: current, past, or unknown
- confidence: 0.0 to 1.0

Focus on durable identity facts. Skip trivial conversation artifacts.

Return a JSON object with a "facts" array."""

    elif variant == "D":
        # Hybrid: structured predicates + subject stripping + temporal precision + few-shot + density directive
        predicates_str = ", ".join(CONSTRAINED_PREDICATES)
        return f"""You are extracting personal facts about a user from their conversation with an AI assistant.

Conversation title: "{conv_title}"

{conv_text}

Extract facts about the USER as structured triples. Maximize information density — every word should carry meaning. No hedging language ("seems to", "appears to", "might be"). If uncertain, lower the confidence score instead of hedging in the text.

For each fact, provide:
- subject: Who the fact is about. Use the person's name if known, otherwise "user".
- predicate: The relationship or attribute. MUST be one of: {predicates_str}
- object: The specific value, entity, or description. Be concrete and precise — names, numbers, and specifics over vague descriptions.
- qualifier: Temporal or conditional context. IMPORTANT: If temporal scope is unclear, mark as "unknown" rather than guessing. Only include qualifiers when you have clear evidence.
- category: One of: preference, biography, project, relationship, interest, skill, value, habit, opinion, goal, negative_trait
- temporal: current, past, or unknown
- confidence: 0.0 to 1.0

Examples of good structured facts:
  {{"subject": "user", "predicate": "married_to", "object": "Jordan", "qualifier": "unknown", "category": "relationship", "temporal": "current", "confidence": 0.95}}
  {{"subject": "user", "predicate": "trades", "object": "US equities, scalping and day trading", "qualifier": "active as of 2024", "category": "interest", "temporal": "current", "confidence": 0.9}}
  {{"subject": "user", "predicate": "founded", "object": "a startup", "qualifier": "did not succeed", "category": "biography", "temporal": "past", "confidence": 0.85}}
  {{"subject": "user", "predicate": "values", "object": "data sovereignty over cloud convenience", "qualifier": "unknown", "category": "value", "temporal": "current", "confidence": 0.9}}

Focus on durable identity facts. Skip trivial conversation artifacts (product lookups, debugging steps, one-off tasks) unless they reveal something lasting about the person.

Return a JSON object with a "facts" array."""

    else:
        raise ValueError(f"Unknown variant: {variant}")


def get_variant_schema(variant):
    """Return JSON schema for the given variant."""
    if variant in ("A", "B"):
        return BASELINE_SCHEMA
    else:
        return STRUCTURED_SCHEMA


# ==========================================================================
# LLM Extraction
# ==========================================================================

def extract_with_llm(prompt, schema):
    """Call Haiku for extraction, parse JSON response.
    Returns (facts_list, input_tokens, output_tokens) or (None, 0, 0) on failure."""
    json_instruction = "Respond with ONLY valid JSON. No explanation, no markdown fences.\n"
    json_instruction += f"Schema: {json.dumps(schema, indent=2)}\n\n"

    try:
        result = call_llm(
            json_instruction + prompt,
            role="extraction",
            max_tokens=2000,
            temperature=0.1,
        )
    except Exception as e:
        print(f"    ERROR: LLM call failed: {e}")
        return None, 0, 0

    raw = result["text"]

    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
        facts = parsed.get("facts", [])
        return facts, result["input_tokens"], result["output_tokens"]
    except json.JSONDecodeError:
        print(f"    ERROR: JSON parse failed")
        return None, result["input_tokens"], result["output_tokens"]


# ==========================================================================
# Fact Text Reconstruction
# ==========================================================================

def get_fact_text(fact, variant):
    """Get displayable fact text from a fact dict."""
    if variant in ("C", "D"):
        parts = []
        subj = fact.get("subject", "")
        pred = fact.get("predicate", "")
        obj = fact.get("object", "")
        qual = fact.get("qualifier", "")
        if subj:
            parts.append(subj)
        if pred:
            parts.append(pred.replace("_", " "))
        if obj:
            parts.append(obj)
        if qual and qual.lower() not in ("unknown", "none", ""):
            parts.append(f"({qual})")
        return " ".join(parts) if parts else ""
    else:
        return fact.get("fact", "")


# ==========================================================================
# Scoring (5 Automated Dimensions)
# ==========================================================================

def score_fact(fact_text):
    """Score a single fact on 5 quality dimensions. Returns dict of scores (0.0-1.0)."""
    if not fact_text or not fact_text.strip():
        return {d: 0.0 for d in SCORE_WEIGHTS}

    words = re.findall(r'\b[a-zA-Z]+\b', fact_text.lower())
    word_count = len(words) if words else 1

    # 1. Lexical Density — ratio of content words to total
    stop_count = sum(1 for w in words if w in STOP_WORDS)
    lexical_density = 1.0 - (stop_count / word_count) if word_count > 0 else 0.0

    # 2. Specificity — capitalized words + numeric tokens / total
    all_tokens = fact_text.split()
    capitalized = sum(1 for t in all_tokens if t and t[0].isupper() and len(t) > 1)
    numeric = sum(1 for t in all_tokens if any(c.isdigit() for c in t))
    specificity = min(1.0, (capitalized + numeric) / max(len(all_tokens), 1))

    # 3. Keyword Extractability — unique non-stop-word tokens
    from score_facts import get_fact_keywords
    keywords = get_fact_keywords(fact_text)
    keyword_extractability = min(1.0, len(keywords) / 4.0)  # 4 keywords = perfect

    # 4. Template Avoidance — binary penalty for template phrases
    fact_lower = fact_text.lower()
    has_template = any(phrase in fact_lower for phrase in TEMPLATE_PHRASES)
    template_avoidance = 0.0 if has_template else 1.0

    # 5. Brevity — shorter facts preferred. 10 words = 1.0, 20 words = 0.5
    brevity = min(1.0, 10.0 / word_count) if word_count > 0 else 1.0

    scores = {
        "lexical_density": round(lexical_density, 3),
        "specificity": round(specificity, 3),
        "keyword_extractability": round(keyword_extractability, 3),
        "template_avoidance": round(template_avoidance, 3),
        "brevity": round(brevity, 3),
    }

    # Weighted aggregate
    aggregate = sum(scores[dim] * weight for dim, weight in SCORE_WEIGHTS.items())
    scores["aggregate"] = round(aggregate, 3)

    return scores


# ==========================================================================
# Generation
# ==========================================================================

def run_generate(variant_filter=None):
    """Run extraction for all/specified variants on test set."""
    if not TEST_SET_FILE.exists():
        print("ERROR: No test set. Run --select-test-set first.")
        return

    EVAL_DIR.mkdir(parents=True, exist_ok=True)

    with open(TEST_SET_FILE, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    conversations = manifest["conversations"]
    variants = [variant_filter] if variant_filter else VARIANTS

    print("=" * 60)
    print("D-056 Extraction Eval — Generating Variants")
    print("=" * 60)
    print(f"Conversations: {len(conversations)}")
    print(f"Variants: {', '.join(variants)}")

    with contextlib.closing(get_db()) as conn:
        for variant in variants:
            results_file = EVAL_DIR / f"extraction_results_{variant}.json"

            # Load existing results for resume support
            existing = {}
            if results_file.exists():
                with open(results_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)

            print(f"\n--- Variant {variant} ---")
            schema = get_variant_schema(variant)
            total_input = 0
            total_output = 0
            start = time.time()

            for i, entry in enumerate(conversations):
                conv_id = entry["conversation_id"]

                # Skip already-generated
                if conv_id in existing.get("results", {}):
                    print(f"  [{i+1}/{len(conversations)}] {entry['title'][:40]}... (cached)")
                    continue

                conv_text = load_conversation_text(conn, conv_id)
                if not conv_text.strip():
                    print(f"  [{i+1}/{len(conversations)}] {entry['title'][:40]}... (no messages)")
                    continue

                conv_title = entry.get("title", "Untitled")
                prompt = build_variant_prompt(variant, conv_title, conv_text)
                facts, inp_tok, out_tok = extract_with_llm(prompt, schema)

                total_input += inp_tok
                total_output += out_tok

                if facts is None:
                    print(f"  [{i+1}/{len(conversations)}] {entry['title'][:40]}... FAILED")
                    continue

                if "results" not in existing:
                    existing["results"] = {}

                existing["results"][conv_id] = {
                    "conversation_id": conv_id,
                    "title": conv_title,
                    "facts": facts,
                    "fact_count": len(facts),
                    "input_tokens": inp_tok,
                    "output_tokens": out_tok,
                }

                print(f"  [{i+1}/{len(conversations)}] {entry['title'][:40]}... "
                      f"{len(facts)} facts")

            elapsed = time.time() - start
            cost = estimate_cost(
                "claude-haiku-4-5-20251001", total_input, total_output
            )

            existing["variant"] = variant
            existing["generated_at"] = time.strftime("%Y-%m-%d %H:%M")
            existing["total_input_tokens"] = existing.get("total_input_tokens", 0) + total_input
            existing["total_output_tokens"] = existing.get("total_output_tokens", 0) + total_output
            existing["estimated_cost_usd"] = round(
                estimate_cost("claude-haiku-4-5-20251001",
                              existing["total_input_tokens"],
                              existing["total_output_tokens"]), 4
            )

            with open(results_file, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)

            total_facts = sum(
                r["fact_count"] for r in existing.get("results", {}).values()
            )
            print(f"\n  Variant {variant}: {total_facts} total facts in {elapsed:.1f}s "
                  f"(~${cost:.4f})")

    print(f"\nGeneration complete. Run --score next.")


# ==========================================================================
# Scoring
# ==========================================================================

def run_score():
    """Score all generated results on 5 quality dimensions."""
    print("=" * 60)
    print("D-056 Extraction Eval — Scoring")
    print("=" * 60)

    all_scores = {}

    for variant in VARIANTS:
        results_file = EVAL_DIR / f"extraction_results_{variant}.json"
        if not results_file.exists():
            print(f"  Variant {variant}: no results file, skipping")
            continue

        with open(results_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        results = data.get("results", {})
        variant_scores = {}
        total_facts = 0

        for conv_id, conv_data in results.items():
            fact_scores = []
            for fact in conv_data.get("facts", []):
                text = get_fact_text(fact, variant)
                if not text.strip():
                    continue
                scores = score_fact(text)
                scores["fact_text"] = text
                fact_scores.append(scores)
                total_facts += 1

            variant_scores[conv_id] = {
                "title": conv_data.get("title", ""),
                "fact_scores": fact_scores,
            }

        all_scores[variant] = variant_scores
        print(f"  Variant {variant}: scored {total_facts} facts")

    scores_file = EVAL_DIR / "extraction_scores.json"
    with open(scores_file, "w", encoding="utf-8") as f:
        json.dump(all_scores, f, indent=2, ensure_ascii=False)

    print(f"\nScores saved to: {scores_file}")
    print("Run --compare next.")


# ==========================================================================
# Comparison
# ==========================================================================

def run_compare():
    """Print comparison table across all scored variants."""
    scores_file = EVAL_DIR / "extraction_scores.json"
    if not scores_file.exists():
        print("ERROR: No scores file. Run --score first.")
        return

    with open(scores_file, "r", encoding="utf-8") as f:
        all_scores = json.load(f)

    print("=" * 60)
    print("D-056 Extraction Eval — Variant Comparison")
    print("=" * 60)

    # Compute per-variant, per-dimension averages
    variant_avgs = {}
    variant_counts = {}

    for variant, conv_scores in all_scores.items():
        dim_totals = {d: 0.0 for d in list(SCORE_WEIGHTS.keys()) + ["aggregate"]}
        total = 0

        for conv_id, conv_data in conv_scores.items():
            for fs in conv_data.get("fact_scores", []):
                for dim in dim_totals:
                    dim_totals[dim] += fs.get(dim, 0.0)
                total += 1

        variant_avgs[variant] = {
            dim: round(dim_totals[dim] / total, 3) if total > 0 else 0.0
            for dim in dim_totals
        }
        variant_counts[variant] = total

    # Print table
    present_variants = sorted(variant_avgs.keys())
    header = f"  {'Dimension':<25s}"
    for v in present_variants:
        header += f"  {v:>8s}"
    print(f"\n{header}")
    print(f"  {'-' * (25 + 10 * len(present_variants))}")

    dimensions = list(SCORE_WEIGHTS.keys()) + ["aggregate"]
    for dim in dimensions:
        label = dim.replace("_", " ").title()
        if dim == "aggregate":
            label = "AGGREGATE"
        row = f"  {label:<25s}"
        for v in present_variants:
            row += f"  {variant_avgs[v].get(dim, 0):>8.3f}"
        print(row)

    # Fact count row
    print(f"  {'-' * (25 + 10 * len(present_variants))}")
    count_row = f"  {'Total Facts':<25s}"
    for v in present_variants:
        count_row += f"  {variant_counts[v]:>8d}"
    print(count_row)

    # Winner
    if variant_avgs:
        winner = max(present_variants, key=lambda v: variant_avgs[v].get("aggregate", 0))
        best_score = variant_avgs[winner]["aggregate"]
        print(f"\n  Winner: Variant {winner} (aggregate {best_score:.3f})")

        # Per-dimension winners
        print(f"\n  Per-dimension winners:")
        for dim in SCORE_WEIGHTS:
            dim_winner = max(present_variants, key=lambda v: variant_avgs[v].get(dim, 0))
            label = dim.replace("_", " ").title()
            print(f"    {label:<25s} → Variant {dim_winner} "
                  f"({variant_avgs[dim_winner][dim]:.3f})")

    # Load cost data
    print(f"\n  Cost breakdown:")
    for v in present_variants:
        results_file = EVAL_DIR / f"extraction_results_{v}.json"
        if results_file.exists():
            with open(results_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            cost = data.get("estimated_cost_usd", 0)
            inp = data.get("total_input_tokens", 0)
            out = data.get("total_output_tokens", 0)
            print(f"    Variant {v}: ${cost:.4f} ({inp:,} in / {out:,} out)")


# ==========================================================================
# Examples
# ==========================================================================

def show_examples(n):
    """Show n random conversation fact comparisons side-by-side."""
    scores_file = EVAL_DIR / "extraction_scores.json"
    if not scores_file.exists():
        print("ERROR: No scores file. Run --score first.")
        return

    with open(scores_file, "r", encoding="utf-8") as f:
        all_scores = json.load(f)

    # Find conversations present in all variants
    present_variants = sorted(all_scores.keys())
    if not present_variants:
        print("No scored variants found.")
        return

    conv_ids = set(all_scores[present_variants[0]].keys())
    for v in present_variants[1:]:
        conv_ids &= set(all_scores[v].keys())

    conv_ids = list(conv_ids)
    if not conv_ids:
        print("No conversations found in all variants.")
        return

    sample = random.sample(conv_ids, min(n, len(conv_ids)))

    for conv_id in sample:
        title = all_scores[present_variants[0]][conv_id].get("title", "Untitled")
        print(f"\n{'=' * 70}")
        print(f"  Conversation: {title}")
        print(f"{'=' * 70}")

        for v in present_variants:
            conv_data = all_scores[v].get(conv_id, {})
            fact_scores = conv_data.get("fact_scores", [])
            avg_agg = (sum(fs.get("aggregate", 0) for fs in fact_scores) / len(fact_scores)
                       if fact_scores else 0)

            print(f"\n  --- Variant {v} ({len(fact_scores)} facts, avg {avg_agg:.3f}) ---")
            for fs in fact_scores[:8]:  # Cap display at 8 facts
                text = fs.get("fact_text", "")[:80]
                agg = fs.get("aggregate", 0)
                tmpl = "T" if fs.get("template_avoidance", 1) == 0 else " "
                print(f"    [{agg:.2f}]{tmpl} {text}")


# ==========================================================================
# Collective Review (Opus Qualitative Assessment)
# ==========================================================================

def run_collective():
    """Run Opus Collective qualitative review across variants."""
    print("=" * 60)
    print("D-056 Extraction Eval — Collective Review (Opus)")
    print("=" * 60)

    # Load results for all variants
    variant_data = {}
    for v in VARIANTS:
        results_file = EVAL_DIR / f"extraction_results_{v}.json"
        if not results_file.exists():
            continue
        with open(results_file, "r", encoding="utf-8") as f:
            variant_data[v] = json.load(f)

    if len(variant_data) < 2:
        print("ERROR: Need at least 2 variants generated. Run --generate first.")
        return

    present_variants = sorted(variant_data.keys())

    # Sample 5 conversations for review (one per bucket if possible)
    if not TEST_SET_FILE.exists():
        print("ERROR: No test set manifest. Run --select-test-set first.")
        return

    with open(TEST_SET_FILE, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # Pick one conversation per bucket for diversity
    buckets = {}
    for entry in manifest["conversations"]:
        bucket = entry["bucket"]
        if bucket not in buckets:
            buckets[bucket] = entry["conversation_id"]

    sample_ids = list(buckets.values())[:5]

    # Build Collective review prompt
    conversation_blocks = []
    for conv_id in sample_ids:
        conv_block = ""
        title = ""

        for v in present_variants:
            results = variant_data[v].get("results", {})
            conv_result = results.get(conv_id, {})
            if not title:
                title = conv_result.get("title", "Untitled")

            facts = conv_result.get("facts", [])
            fact_lines = []
            for fact in facts[:12]:  # Cap at 12 for token budget
                if v in ("C", "D"):
                    text = get_fact_text(fact, v)
                else:
                    text = fact.get("fact", "")
                if text:
                    fact_lines.append(f"    - {text}")

            conv_block += f"\n  Variant {v} ({len(facts)} facts):\n"
            conv_block += "\n".join(fact_lines) if fact_lines else "    (no facts)"
            conv_block += "\n"

        conversation_blocks.append(
            f"\n### Conversation: \"{title}\"\n{conv_block}"
        )

    conversations_text = "\n".join(conversation_blocks)

    collective_prompt = f"""You are the Collective — the quality and coherence authority for a personal AI memory system. You review with four adversarial personas, each evaluating independently.

CONTEXT: This system extracts facts about a person from their conversations, then uses those facts to build identity layers (ANCHORS: epistemic axioms, CORE: communication guide, PREDICTIONS: behavioral forecasts). Extraction quality bounds ALL downstream — scoring, tiering, retrieval, and layer authoring are capped by fact quality.

Four extraction prompt variants were tested on the same conversations:
- Variant A: Baseline — free-text "fact" field, 8-field schema, no structural constraints
- Variant B: Subject-stripped — "The user is" prefix removed via few-shot examples, same schema
- Variant C: Structured predicates — {{subject, predicate, object, qualifier}} with constrained vocabulary (~30 verbs)
- Variant D: Hybrid — structured predicates + subject stripping + temporal precision directive + few-shot + density maximization

Below are the extraction results for sample conversations across all variants.

{conversations_text}

---

Evaluate from the four Collective personas. Each scores 0-100 independently.

## 1. COGNITIVE SCIENTIST
Is the extraction architecture sound? Do the extracted facts reflect genuine cognitive/behavioral distinctions, or just repackaged conversation topics?

**Checks:**
- Do facts represent real cognitive structures (values, behavioral patterns) vs surface observations?
- Is there over-inference from thin data — facts that claim more than the conversation supports?
- Do structured variants (C/D) lose behavioral nuance by forcing predicate constraints, or do they sharpen it?
- Which variant best distinguishes identity-significant facts from conversational noise?

## 2. NARRATIVE BIOGRAPHER
Could you reconstruct a real person from these facts, or just a taxonomy? Do the facts capture a recognizable human?

**Checks:**
- Would the subject recognize themselves from each variant's facts?
- Which variant produces facts with narrative texture vs clinical descriptions?
- Are there facts that distinguish THIS person from anyone else, or could they describe a generic user?
- Does subject stripping (B) or structured predicates (C/D) preserve or destroy the human signal?

## 3. EPISTEMOLOGIST
Are knowledge claims justified by the conversation? Any over-confident assertions? Hedging masquerading as facts?

**Checks:**
- Every fact should trace to evidence in the conversation (faithful extraction, not invention)
- Are confidence scores calibrated — low confidence for weak signals, high for explicit statements?
- Does any variant produce facts that contradict each other within the same conversation?
- Temporal claims: does each variant correctly distinguish current vs past vs unknown?
- Hedging language ("seems to", "appears to", "is considering") — which variant eliminates it vs preserves it?

## 4. PRAGMATIC ENGINEER
Which variant's output best serves the downstream pipeline? Token efficiency. Actionable facts. No deadweight.

**Checks:**
- Scoring compatibility: The scoring algorithm uses keyword co-occurrence across conversations. Which variant produces facts with the best keyword extractability?
- Tier classification: Which variant makes identity/situational/context classification easiest?
- Deduplication: Which variant is easiest to deduplicate across conversations?
- Layer authoring: Which variant's facts would compose into identity text most naturally?
- Migration cost: What pipeline changes would each non-A variant require?
- Token efficiency: Information per token — shorter facts with same signal are better.

## SYNTHESIS

After all four personas score independently:

```json
{{
  "scores": {{
    "cognitive_scientist": {{"score": <0-100>, "winner": "<A/B/C/D>", "critical_issue": "..."}},
    "narrative_biographer": {{"score": <0-100>, "winner": "<A/B/C/D>", "critical_issue": "..."}},
    "epistemologist": {{"score": <0-100>, "winner": "<A/B/C/D>", "critical_issue": "..."}},
    "pragmatic_engineer": {{"score": <0-100>, "winner": "<A/B/C/D>", "critical_issue": "..."}}
  }},
  "combined": <average>,
  "overall_winner": "<A/B/C/D>",
  "confidence": "<high/medium/low>",
  "ranking": ["1st", "2nd", "3rd", "4th"],
  "critical_finding": "The single most important insight from this comparison",
  "migration_recommendation": "What changes if the winner isn't Variant A"
}}
```

Be specific — cite individual facts as evidence for claims. No generic observations."""

    print(f"\nSending to Opus for Collective review...")
    print(f"  Sample conversations: {len(sample_ids)}")
    print(f"  Variants compared: {', '.join(present_variants)}")

    start = time.time()
    try:
        result = call_llm(
            collective_prompt,
            role="review",
            max_tokens=4000,
            temperature=0.3,
        )
    except Exception as e:
        print(f"ERROR: Collective review failed: {e}")
        return

    elapsed = time.time() - start
    cost = estimate_cost(result["model"], result["input_tokens"], result["output_tokens"])

    print(f"\n  Collective review completed in {elapsed:.1f}s")
    print(f"  Cost: ${cost:.4f} ({result['input_tokens']:,} in / {result['output_tokens']:,} out)")

    # Display review
    print(f"\n{'=' * 70}")
    print("COLLECTIVE REVIEW")
    print(f"{'=' * 70}\n")
    print(result["text"])

    # Save review
    review_file = EVAL_DIR / "extraction_collective_review.md"
    with open(review_file, "w", encoding="utf-8") as f:
        f.write(f"# D-056 Extraction Eval — Collective Review\n\n")
        f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"Model: {result['model']}\n")
        f.write(f"Cost: ${cost:.4f}\n")
        f.write(f"Variants compared: {', '.join(present_variants)}\n")
        f.write(f"Sample conversations: {len(sample_ids)}\n\n---\n\n")
        f.write(result["text"])

    print(f"\nReview saved to: {review_file}")


# ==========================================================================
# Main
# ==========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="D-056 Extraction Prompt Eval Harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python eval_extraction.py --select-test-set       # Pick 20 conversations
  python eval_extraction.py --generate               # Run all 4 variants
  python eval_extraction.py --generate --variant B   # Run single variant
  python eval_extraction.py --score                  # Score all results
  python eval_extraction.py --compare                # Comparison table
  python eval_extraction.py --examples 5             # Side-by-side facts
  python eval_extraction.py --collective             # Opus qualitative review
""",
    )

    parser.add_argument("--select-test-set", action="store_true",
                        help="Auto-select 20 conversations for testing")
    parser.add_argument("--generate", action="store_true",
                        help="Run extraction with all variants (or --variant X)")
    parser.add_argument("--variant", type=str, choices=VARIANTS,
                        help="Run only this variant (with --generate)")
    parser.add_argument("--score", action="store_true",
                        help="Score all generated results")
    parser.add_argument("--compare", action="store_true",
                        help="Print comparison table")
    parser.add_argument("--examples", type=int, metavar="N",
                        help="Show N random fact comparisons")
    parser.add_argument("--collective", action="store_true",
                        help="Run Opus Collective qualitative review")

    args = parser.parse_args()

    if args.select_test_set:
        select_test_conversations()
    elif args.generate:
        run_generate(variant_filter=args.variant)
    elif args.score:
        run_score()
    elif args.compare:
        run_compare()
    elif args.examples is not None:
        show_examples(args.examples)
    elif args.collective:
        run_collective()
    else:
        parser.print_help()


if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    main()
