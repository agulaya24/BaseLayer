#!/usr/bin/env python3
"""
Serving Engine — The core logic for behavioral alignment serving.

Loads spec, retrieves facts (Mem0-style and behavioral), generates responses,
computes diffs. Used by serving_tui.py (visual) and CLI mode below.

Usage (CLI):
    python runners/serving_engine.py "what makes base layer special?"
    python runners/serving_engine.py --steps 4,5 "should I take this job?"
    python runners/serving_engine.py --batch prompts.txt
"""

import sys
import os
import json
import argparse
import sqlite3
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import anthropic
from openai import OpenAI as OpenAIClient
import numpy as np
from sentence_transformers import SentenceTransformer

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
SUBJECTS_DIR = PROJECT_ROOT.parent / "subjects"
OUTPUT_DIR = DEFAULT_DATA_DIR / "experiments" / "serving_layer"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def resolve_subject_paths(subject=None):
    """Resolve data paths for a subject. None = default (Aarik)."""
    if subject and subject != "default":
        base = SUBJECTS_DIR / f"{subject}_memory" / "data"
        if not base.exists():
            raise FileNotFoundError(f"Subject '{subject}' not found at {base}")
    else:
        base = DEFAULT_DATA_DIR

    layers_dir = base / "identity_layers"
    db_file = base / "database" / "memory.db"
    cache_dir = OUTPUT_DIR / "cache" / (subject or "default")
    cache_dir.mkdir(parents=True, exist_ok=True)

    return layers_dir, db_file, cache_dir


# ── Spec & Facts ────────────────────────────────────────────────────────────

def load_spec(layers_dir=None):
    """Load full behavioral specification from layer files."""
    if layers_dir is None:
        layers_dir = DEFAULT_DATA_DIR / "identity_layers"
    sections = []
    for layer_name, filename in [
        ("ANCHORS", "anchors_v4.md"),
        ("CORE", "core_v4.md"),
        ("PREDICTIONS", "predictions_v4.md"),
    ]:
        filepath = layers_dir / filename
        if not filepath.exists():
            continue
        content = filepath.read_text(encoding="utf-8")
        marker = "## Injectable Block"
        idx = content.find(marker)
        if idx >= 0:
            block = content[idx + len(marker):].strip()
        else:
            sep = content.find("\n---\n")
            block = content[sep + 5:].strip() if sep >= 0 else content.strip()
        sections.append(f"## {layer_name}\n\n{block}")
    return "\n\n".join(sections)


def load_facts(db_file=None):
    """Load behavioral facts from SQLite."""
    if db_file is None:
        db_file = DEFAULT_DATA_DIR / "database" / "memory.db"
    if not db_file.exists():
        return []
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    cols = [row[1] for row in conn.execute("PRAGMA table_info(memory_facts)").fetchall()]
    tier_col = "knowledge_tier" if "knowledge_tier" in cols else "tier"
    active_filter = "AND active = 1" if "active" in cols else ""
    query = f"""
        SELECT id, fact_text, predicate, {tier_col} as tier
        FROM memory_facts WHERE 1=1 {active_filter}
        AND {tier_col} IN ('identity', 'behavioral')
    """
    rows = conn.execute(query).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Embeddings (cached) ─────────────────────────────────────────────────────

class EmbeddingStore:
    """Manages embeddings for both MiniLM (Base Layer) and OpenAI (Mem0)."""

    def __init__(self, facts):
        self.facts = facts
        self.fact_texts = [f["fact_text"] for f in facts]
        self.minilm_model = None
        self.minilm_embeddings = None
        self.openai_client = None
        self.openai_embeddings = None

    def load(self, on_status=None, cache_dir=None):
        """Load or compute embeddings. Uses disk cache."""
        if cache_dir is None:
            cache_dir = OUTPUT_DIR / "cache" / "default"
            cache_dir.mkdir(parents=True, exist_ok=True)
        minilm_cache = cache_dir / "fact_embeddings_minilm.npy"
        openai_cache = cache_dir / "fact_embeddings_openai.npy"
        cache_count = cache_dir / "fact_count.txt"

        cache_valid = (
            minilm_cache.exists() and openai_cache.exists() and cache_count.exists()
            and cache_count.read_text().strip() == str(len(self.facts))
        )

        if on_status:
            on_status("Loading MiniLM...")
        self.minilm_model = SentenceTransformer("all-MiniLM-L6-v2")
        self.openai_client = OpenAIClient()

        if cache_valid:
            if on_status:
                on_status("Loading cached embeddings...")
            self.minilm_embeddings = np.load(str(minilm_cache))
            self.openai_embeddings = np.load(str(openai_cache))
        else:
            if on_status:
                on_status("Computing embeddings (cached for next time)...")

            self.minilm_embeddings = self.minilm_model.encode(
                self.fact_texts, show_progress_bar=False
            )

            all_embs = []
            for i in range(0, len(self.facts), 100):
                batch = self.fact_texts[i:i+100]
                resp = self.openai_client.embeddings.create(
                    input=[t.replace("\n", " ") for t in batch],
                    model="text-embedding-3-small"
                )
                all_embs.append(np.array([d.embedding for d in resp.data]))
                if on_status and i % 500 == 0 and i > 0:
                    on_status(f"  ...{i}/{len(self.facts)}")
            self.openai_embeddings = np.vstack(all_embs)

            np.save(str(minilm_cache), self.minilm_embeddings)
            np.save(str(openai_cache), self.openai_embeddings)
            cache_count.write_text(str(len(self.facts)))

    def retrieve(self, query_embedding, embeddings, top_k=10):
        """Top-K cosine similarity retrieval."""
        query_norm = query_embedding / np.linalg.norm(query_embedding)
        fact_norms = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
        sims = np.dot(fact_norms, query_norm)
        top_idx = np.argsort(sims)[-top_k:][::-1]
        return [
            {
                "fact_text": self.facts[idx]["fact_text"],
                "predicate": self.facts[idx].get("predicate", ""),
                "similarity": float(sims[idx]),
            }
            for idx in top_idx
        ]

    def mem0_retrieve(self, raw_query, top_k=10):
        """Mem0-faithful: text-embedding-3-small, raw query, cosine top-K."""
        emb = np.array(
            self.openai_client.embeddings.create(
                input=[raw_query.replace("\n", " ")],
                model="text-embedding-3-small"
            ).data[0].embedding
        )
        return self.retrieve(emb, self.openai_embeddings, top_k)

    def behavioral_retrieve(self, behavioral_query, top_k=10):
        """Base Layer: MiniLM embedding of behaviorally-interpreted query."""
        emb = self.minilm_model.encode(behavioral_query)
        return self.retrieve(emb, self.minilm_embeddings, top_k)


# ── Model calls ─────────────────────────────────────────────────────────────

def call_model(client, statement, system_prompt, model="claude-sonnet-4-20250514", max_tokens=1024):
    """Call Claude."""
    response = client.messages.create(
        model=model, max_tokens=max_tokens, temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": statement}],
    )
    return response.content[0].text


def get_behavioral_interpretation(client, statement, spec, model="claude-sonnet-4-20250514"):
    """Rewrite query through behavioral lens."""
    system = (
        "You have a behavioral specification of the person asking this question. "
        "Based on their reasoning patterns, values, and behavioral triggers, "
        "rewrite their question as a search query that captures what they're "
        "ACTUALLY asking. Output ONLY the rewritten query. One sentence.\n\n"
        f"{spec}"
    )
    return call_model(client, statement, system, model=model, max_tokens=150).strip()


def get_spec_activation(client, statement, spec, model="claude-sonnet-4-20250514"):
    """Identify which spec sections activated for this statement."""
    system = (
        "You have a behavioral specification with these sections. "
        "Given the user's statement, identify which sections ACTIVATED "
        "(influenced how you would respond). For each activated section, "
        "give: the section name, one sentence explaining WHY it's relevant. "
        "Format: SECTION_NAME: reason\n"
        "Only list sections that are genuinely relevant. Be selective.\n\n"
        f"{spec}"
    )
    return call_model(client, statement, system, model=model, max_tokens=500).strip()


# ── System prompts ──────────────────────────────────────────────────────────

def spec_system_prompt(spec, facts_context=""):
    """Build system prompt with behavioral spec + optional facts."""
    base = (
        "You are an AI assistant. The following behavioral specification describes "
        "the person you are talking to. Use it to calibrate every response. Never "
        "reference the specification directly. Modulate naturally.\n\n"
        f"{spec}"
    )
    if facts_context:
        base += f"\n\n## Supporting facts\n\n{facts_context}"
    return base


def mem0_system_prompt(facts_context):
    """Build system prompt mimicking Mem0 (facts, no spec)."""
    return (
        "You are a helpful AI assistant. You have the following memories "
        "about the person you're talking to:\n\n" + facts_context
    )


def shadow_system_prompt():
    """Baseline: no spec, no facts."""
    return "You are a helpful AI assistant. Respond naturally and helpfully."


def format_facts(facts):
    """Format facts as numbered list."""
    return "\n".join(f"{i}. {f['fact_text']}" for i, f in enumerate(facts, 1))


# ── Diff cascade ────────────────────────────────────────────────────────────

def run_cascade(statement, spec, store, client, top_k=10, model="claude-sonnet-4-20250514",
                on_status=None, on_behavioral_query=None, on_mem0_facts=None,
                on_bl_facts=None, on_divergence=None, on_spec_activation=None,
                on_mem0_response=None, on_bl_response=None, on_merged_response=None):
    """Run the full diff cascade with per-step callbacks for live display."""

    def fire(cb, data):
        if cb:
            cb(data)

    def status(msg):
        fire(on_status, msg)

    result = {
        "statement": statement,
        "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "model": model,
    }

    # 1. Behavioral interpretation
    status("Getting behavioral interpretation...")
    behavioral_query = get_behavioral_interpretation(client, statement, spec, model=model)
    result["behavioral_query"] = behavioral_query
    fire(on_behavioral_query, behavioral_query)

    # 2. Mem0 retrieval
    status("Mem0 retrieval...")
    mem0_facts = store.mem0_retrieve(statement, top_k=top_k)
    result["mem0_facts"] = mem0_facts
    fire(on_mem0_facts, mem0_facts)

    # 3. Base Layer retrieval
    status("Base Layer retrieval...")
    bl_facts = store.behavioral_retrieve(behavioral_query, top_k=top_k)
    result["bl_facts"] = bl_facts
    fire(on_bl_facts, bl_facts)

    # 4. Divergence
    mem0_texts = {f["fact_text"] for f in mem0_facts}
    bl_texts = {f["fact_text"] for f in bl_facts}
    shared = mem0_texts & bl_texts
    only_mem0 = mem0_texts - bl_texts
    only_bl = bl_texts - mem0_texts
    divergence = {
        "shared": len(shared),
        "only_mem0": len(only_mem0),
        "only_bl": len(only_bl),
        "total_unique": len(mem0_texts | bl_texts),
        "only_mem0_snippets": [t[:80] for t in list(only_mem0)[:3]],
        "only_bl_snippets": [t[:80] for t in list(only_bl)[:3]],
    }
    result["divergence"] = divergence
    fire(on_divergence, divergence)

    # 5. Spec activation
    status("Detecting spec activation...")
    activation_raw = get_spec_activation(client, statement, spec, model=model)
    result["spec_activation"] = activation_raw
    fire(on_spec_activation, activation_raw)

    # 6. Generate responses (each fires its callback immediately)
    status("Generating Mem0 response...")
    mem0_response = call_model(
        client, statement,
        mem0_system_prompt(format_facts(mem0_facts)),
        model=model,
    )
    result["mem0_response"] = mem0_response
    fire(on_mem0_response, mem0_response)

    status("Generating Base Layer response...")
    bl_response = call_model(
        client, statement,
        spec_system_prompt(spec, format_facts(bl_facts)),
        model=model,
    )
    result["bl_response"] = bl_response
    fire(on_bl_response, bl_response)

    # Merged: behavioral facts + domain facts, deduplicated, with spec
    bl_texts_set = {f["fact_text"] for f in bl_facts}
    merged_facts = list(bl_facts)
    for f in mem0_facts:
        if f["fact_text"] not in bl_texts_set:
            merged_facts.append(f)
    result["merged_facts"] = merged_facts
    result["merged_fact_count"] = len(merged_facts)

    status("Generating merged response...")
    merged_response = call_model(
        client, statement,
        spec_system_prompt(spec, format_facts(merged_facts)),
        model=model,
    )
    result["merged_response"] = merged_response
    fire(on_merged_response, merged_response)

    # 7. Delta metrics
    markers = ["you're", "you are", "your ", "you need", "you know"]
    result["delta"] = {
        "mem0_words": len(mem0_response.split()),
        "bl_words": len(bl_response.split()),
        "merged_words": len(merged_response.split()),
        "mem0_confrontation": sum(1 for m in markers if m in mem0_response.lower()),
        "bl_confrontation": sum(1 for m in markers if m in bl_response.lower()),
        "merged_confrontation": sum(1 for m in markers if m in merged_response.lower()),
        "mem0_questions": mem0_response.count("?"),
        "bl_questions": bl_response.count("?"),
        "merged_questions": merged_response.count("?"),
        "mem0_lists": mem0_response.count("- ") + mem0_response.count("* "),
        "bl_lists": bl_response.count("- ") + bl_response.count("* "),
        "merged_lists": merged_response.count("- ") + merged_response.count("* "),
    }

    status("Done.")

    # Save
    output_file = OUTPUT_DIR / f"cascade_{result['timestamp']}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)
    result["output_file"] = str(output_file)

    return result


# ── CLI mode ────────────────────────────────────────────────────────────────

def print_cascade(r):
    """Print cascade results to console."""
    w = 78
    print(f"\n{'=' * w}")
    print(f"  SERVING LAYER - THE DIFF CASCADE")
    print(f"{'=' * w}")
    print(f"\n  Statement: {r['statement']}")
    print(f"  Behavioral: {r['behavioral_query']}")

    print(f"\n{'-' * w}")
    print(f"  MEM0 FACTS:")
    for f in r['mem0_facts'][:5]:
        print(f"    {f['similarity']:.3f}  {f['fact_text'][:65]}")
    print(f"\n  BASE LAYER FACTS:")
    for f in r['bl_facts'][:5]:
        print(f"    {f['similarity']:.3f}  {f['fact_text'][:65]}")

    d = r['divergence']
    print(f"\n  DIVERGENCE: {d['only_mem0']+d['only_bl']}/{d['total_unique']} facts differ")
    print(f"    Shared: {d['shared']} | Only Mem0: {d['only_mem0']} | Only BL: {d['only_bl']}")

    print(f"\n{'-' * w}")
    print(f"  SPEC ACTIVATION:")
    for line in r['spec_activation'].split("\n"):
        if line.strip():
            print(f"    {line.strip()}")

    print(f"\n{'-' * w}")
    print(f"  MEM0 RESPONSE:")
    for line in r['mem0_response'].split("\n"):
        print(f"    {line}")

    print(f"\n{'-' * w}")
    print(f"  BASE LAYER RESPONSE:")
    for line in r['bl_response'].split("\n"):
        print(f"    {line}")

    dl = r['delta']
    print(f"\n{'-' * w}")
    print(f"  DELTA:")
    print(f"    Words:         Mem0={dl['mem0_words']} BL={dl['bl_words']}")
    print(f"    Confrontation: Mem0={dl['mem0_confrontation']} BL={dl['bl_confrontation']}")
    print(f"    Questions:     Mem0={dl['mem0_questions']} BL={dl['bl_questions']}")
    print(f"    Lists:         Mem0={dl['mem0_lists']} BL={dl['bl_lists']}")
    print(f"\n  Saved: {r.get('output_file', 'N/A')}")
    print(f"{'=' * w}")


def main():
    parser = argparse.ArgumentParser(description="Serving Engine — The Diff Cascade")
    parser.add_argument("statement", nargs="?")
    parser.add_argument("--model", default="claude-sonnet-4-20250514")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--subject", default=None, help="Subject name (e.g. buffett, marks). Default = Aarik")
    parser.add_argument("--batch", help="File with one statement per line")
    args = parser.parse_args()

    if args.batch:
        statements = Path(args.batch).read_text().strip().split("\n")
    elif args.statement:
        statements = [args.statement]
    else:
        print("\n  Enter a statement:")
        s = input("  > ").strip()
        if not s:
            return
        statements = [s]

    layers_dir, db_file, cache_dir = resolve_subject_paths(args.subject)
    spec = load_spec(layers_dir)
    facts = load_facts(db_file)
    store = EmbeddingStore(facts)
    store.load(on_status=lambda m: print(f"  {m}"), cache_dir=cache_dir)
    client = anthropic.Anthropic()
    print(f"  Subject: {args.subject or 'default'} | Facts: {len(facts)} | Spec: ~{int(len(spec.split())*1.3)} tokens")

    for statement in statements:
        result = run_cascade(
            statement, spec, store, client,
            top_k=args.top_k, model=args.model,
            on_status=lambda m: print(f"  {m}"),
        )
        print_cascade(result)


if __name__ == "__main__":
    main()
