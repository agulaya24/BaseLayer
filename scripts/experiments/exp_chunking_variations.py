"""
Experiment 2: Chunking Variations
==================================
Question: Does chunking strategy affect extraction quality? Current: paragraph-boundary, 500-char overlap.

Method:
  - Extract Franklin (10 chapters) with 4 chunking strategies
  - Same Qwen model, same predicates, only chunking differs
  - Compare: fact count, unique facts, redundancy rate

Conditions:
  A. Current: paragraph-boundary, 500-char overlap (baseline)
  B. No overlap: paragraph-boundary, 0 overlap
  C. Large overlap: paragraph-boundary, 1000-char overlap
  D. Sentence-level: split on sentence boundaries, 2-sentence overlap
"""

import json
import re
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.dirname(__file__))

from ollama_utils import call_qwen, get_franklin_conversations, save_results

PREDICATES = [
    "owns", "values", "practices", "studies", "prefers", "avoids",
    "works_at", "lives_in", "married_to", "raised_in", "graduated_from",
    "manages", "builds", "trades", "believes", "fears", "enjoys",
    "dislikes", "struggles_with", "excels_at", "identifies_as",
    "maintains", "follows", "aspires_to", "lost", "founded",
    "parents", "experienced", "learned", "decided", "prioritizes",
    "unknown", "attended", "interested_in", "wants_to", "loves", "hates",
    "plays", "monitors", "relates_to", "collaborates_with", "mentored_by",
    "raised_by", "friends_with", "reports_to", "admires", "conflicts_with",
]


def chunk_paragraph_overlap(text: str, max_chars: int = 6000, overlap: int = 500) -> list[str]:
    """Chunk on paragraph boundaries with configurable overlap."""
    paragraphs = text.split("\n\n")
    chunks = []
    current = []
    current_len = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if current_len + len(para) > max_chars and current:
            chunks.append("\n\n".join(current))
            # Keep overlap from end of current chunk
            if overlap > 0:
                overlap_text = "\n\n".join(current)
                overlap_paras = []
                ol = 0
                for p in reversed(current):
                    if ol + len(p) > overlap:
                        break
                    overlap_paras.insert(0, p)
                    ol += len(p)
                current = overlap_paras
                current_len = sum(len(p) for p in current)
            else:
                current = []
                current_len = 0
        current.append(para)
        current_len += len(para)

    if current:
        chunks.append("\n\n".join(current))
    return chunks


def chunk_sentence_level(text: str, sentences_per_chunk: int = 15, overlap_sentences: int = 2) -> list[str]:
    """Chunk on sentence boundaries with sentence-level overlap."""
    # Simple sentence splitting
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    chunks = []
    i = 0
    while i < len(sentences):
        end = min(i + sentences_per_chunk, len(sentences))
        chunk = " ".join(sentences[i:end])
        chunks.append(chunk)
        i = end - overlap_sentences if overlap_sentences > 0 and end < len(sentences) else end

    return chunks


CHUNKING_STRATEGIES = {
    "A_para_500overlap": lambda t: chunk_paragraph_overlap(t, overlap=500),
    "B_para_no_overlap": lambda t: chunk_paragraph_overlap(t, overlap=0),
    "C_para_1000overlap": lambda t: chunk_paragraph_overlap(t, overlap=1000),
    "D_sentence_level": lambda t: chunk_sentence_level(t, sentences_per_chunk=15, overlap_sentences=2),
}


def extract_from_chunks(chunks: list[str], label: str) -> dict:
    """Extract facts from a list of text chunks."""
    all_facts = []
    errors = 0
    pred_list = ", ".join(PREDICATES)

    for i, chunk in enumerate(chunks):
        if len(chunk.strip()) < 100:
            continue
        print(f"    [{label}] chunk {i+1}/{len(chunks)} ({len(chunk)} chars)...")

        prompt = f"""Extract structured facts about the person described in this text.

PREDICATES (use ONLY these): {pred_list}

For each fact, return JSON with: subject, predicate, object, confidence (0.0-1.0).
Return a JSON object with a "facts" array. Extract up to 20 facts per chunk.

TEXT:
{chunk[:8000]}

Return ONLY valid JSON."""

        try:
            response = call_qwen(prompt, max_tokens=3000, json_mode=True)
            data = json.loads(response)
            facts = data.get("facts", [])
            for f in facts:
                all_facts.append({
                    "predicate": f.get("predicate", "unknown"),
                    "object": f.get("object", ""),
                    "confidence": f.get("confidence", 0.5),
                    "chunk_idx": i,
                })
        except (json.JSONDecodeError, KeyError) as e:
            errors += 1

    # Measure redundancy: facts with identical predicate+object
    fact_signatures = [f"{f['predicate']}:{str(f.get('object', '')).lower().strip()}" for f in all_facts]
    unique_sigs = set(fact_signatures)
    redundancy_rate = 1 - (len(unique_sigs) / max(len(fact_signatures), 1))

    return {
        "label": label,
        "chunks_processed": len(chunks),
        "total_facts": len(all_facts),
        "unique_facts": len(unique_sigs),
        "redundancy_rate": round(redundancy_rate, 3),
        "parse_errors": errors,
        "facts": all_facts,
    }


def main():
    print("=" * 60)
    print("EXPERIMENT 2: Chunking Variations")
    print("=" * 60)

    conversations = get_franklin_conversations(limit=10)
    if not conversations:
        print("ERROR: No Franklin conversations found")
        return

    # Combine all text for chunking experiments
    full_text = "\n\n".join(c["text"] for c in conversations)
    print(f"Total text: {len(full_text):,} chars from {len(conversations)} chapters")
    print()

    results = {}
    for strategy_name, chunker in CHUNKING_STRATEGIES.items():
        print(f"--- {strategy_name} ---")
        t0 = time.time()
        chunks = chunker(full_text)
        print(f"  Chunks created: {len(chunks)} (avg {sum(len(c) for c in chunks)//max(len(chunks),1)} chars)")

        result = extract_from_chunks(chunks, strategy_name)
        result["time_seconds"] = round(time.time() - t0, 1)
        result["avg_chunk_size"] = sum(len(c) for c in chunks) // max(len(chunks), 1)
        results[strategy_name] = result

        print(f"  Facts: {result['total_facts']}, Unique: {result['unique_facts']}, "
              f"Redundancy: {result['redundancy_rate']:.1%}, Time: {result['time_seconds']}s")
        print()

    # Summary comparison
    summary = {
        "experiment": "chunking_variations",
        "question": "Does chunking strategy affect extraction quality?",
        "total_input_chars": len(full_text),
        "conditions": {},
    }

    print("=" * 60)
    print("SUMMARY")
    print(f"{'Strategy':<25} {'Chunks':>6} {'Facts':>6} {'Unique':>6} {'Redund':>8} {'Time':>6}")
    print("-" * 60)
    for name, r in results.items():
        print(f"{name:<25} {r['chunks_processed']:>6} {r['total_facts']:>6} "
              f"{r['unique_facts']:>6} {r['redundancy_rate']:>7.1%} {r['time_seconds']:>5.0f}s")
        summary["conditions"][name] = {
            "chunks": r["chunks_processed"],
            "total_facts": r["total_facts"],
            "unique_facts": r["unique_facts"],
            "redundancy_rate": r["redundancy_rate"],
            "time_seconds": r["time_seconds"],
        }
    print("=" * 60)

    summary["full_results"] = results
    save_results("chunking_variations", summary)


if __name__ == "__main__":
    main()
